#!/usr/bin/env python3
"""Train the AI partner with PPO (self-play + bot partners), no UI, as fast as the CPU can go.

    nix develop --command python3 ml/train.py --run ml/runs/v1 --hours 1
    nix develop --command python3 ml/train.py --run ml/runs/v1 --hours 4 --resume

Worker processes run the game worlds; the main process runs the network.
Torch is imported only after the workers are forked, so they stay small.
"""
import argparse
import collections
import copy
import csv
import multiprocessing as mp
import os
import random
import signal
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import env as E  # noqa: E402


# ---- parallel worlds -------------------------------------------------------------
def _pack(obs):
    """grid (0/1 bytes, packed to bits: 6.5x less to send), vec, mask, past."""
    return (np.packbits(np.stack([o[0] for o in obs]), axis=-1),) + tuple(np.stack([o[k] for o in obs]) for k in (1, 2, 3))


def _unpack(o):
    return (np.unpackbits(o[0], axis=-1, count=E.GRID),) + tuple(o[1:])


def _worker(conn, n, seed, stages, maps=None):
    signal.signal(signal.SIGINT, signal.SIG_IGN)     # Ctrl-C: the main process stops cleanly
    random.seed(seed)
    np.random.seed(seed)
    E.init_pygame()
    A = E.load_assets(maps)
    envs = [E.TankEnv(A, stages) for _ in range(n)]
    obs = [e.reset() for e in envs]
    conn.send(_pack(obs))
    while True:
        cmd, data = conn.recv()
        if cmd == "close":
            return
        rews, dones, infos = np.zeros((n, 2), np.float32), np.zeros(n, bool), []
        for i, e in enumerate(envs):
            rews[i], dones[i] = e.step(data[i])
            if dones[i]:
                infos.append(dict(e.stats))
                obs[i] = e.reset()
            else:
                obs[i] = e.obs()
        conn.send((_pack(obs), rews, dones, infos))


class VecEnv:
    def __init__(self, workers, per_worker, seed, stages, start="auto", maps=None):
        # Linux: fork (fast; torch is not imported yet). macOS: spawn (fork is not safe there).
        if start == "auto":
            start = "fork" if sys.platform.startswith("linux") else "spawn"
        ctx = mp.get_context(start)
        self.conns, self.procs = [], []
        for i in range(workers):
            a, b = ctx.Pipe()
            p = ctx.Process(target=_worker, args=(b, per_worker, seed * 1000 + i, stages, maps), daemon=True)
            p.start()
            b.close()                   # only the worker keeps its end: a dead worker gives EOF here
            self.conns.append(a)
            self.procs.append(p)
        self.first = [c.recv() for c in self.conns]
        self.n = workers * per_worker

    def reset(self):
        return tuple(np.concatenate(x) for x in zip(*[_unpack(f) for f in self.first]))

    def step(self, actions):
        """actions: int array [n_envs, 2]."""
        per = len(actions) // len(self.conns)
        for i, c in enumerate(self.conns):
            c.send(("step", actions[i * per:(i + 1) * per]))
        res = []
        for i, c in enumerate(self.conns):
            try:
                res.append(c.recv())
            except EOFError:
                raise RuntimeError("worker %d died (its error is printed above)" % i) from None
        obs = tuple(np.concatenate(x) for x in zip(*[_unpack(r[0]) for r in res]))
        rews = np.concatenate([r[1] for r in res])
        dones = np.concatenate([r[2] for r in res])
        infos = [i for r in res for i in r[3]]
        return obs, rews, dones, infos

    def close(self):
        for c in self.conns:
            try:
                c.send(("close", None))
            except OSError:
                pass


# ---- PPO ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=os.path.join(HERE, "runs", "v1"))
    ap.add_argument("--hours", type=float, default=1.0, help="time budget")
    ap.add_argument("--workers", type=int, default=max(2, min(10, (os.cpu_count() or 4) - 2)))
    ap.add_argument("--mp-start", default="auto", choices=("auto", "fork", "spawn"),
                    help="worker start method (auto: fork on Linux, spawn on macOS)")
    ap.add_argument("--device", default="auto", help="auto (cuda > mps > cpu), cuda, mps or cpu")
    ap.add_argument("--envs-per-worker", type=int, default=16, help="worlds per worker (speed test: README)")
    ap.add_argument("--threads", type=int, default=8, help="torch CPU threads")
    ap.add_argument("--steps", type=int, default=64, help="rollout length per update (worlds x steps ~ 1024)")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--minibatch", type=int, default=2048)
    ap.add_argument("--lr", type=float, default=2.5e-4, help="learning rate at the start")
    ap.add_argument("--lr-end", type=float, default=None, help="learning rate after --lr-frames (default: = --lr)")
    ap.add_argument("--lr-frames", type=float, default=4e9,
                    help="the rate goes down linearly from --lr to --lr-end over this many frames (from the run's frame count, so a resume keeps it)")
    ap.add_argument("--arch", default="small", choices=("small", "big"),
                    help="network size of a new run (a resume keeps the size of its checkpoint)")
    ap.add_argument("--gamma", type=float, default=0.99)
    ap.add_argument("--lam", type=float, default=0.95)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--ent", type=float, default=0.01)
    ap.add_argument("--stages", default="1-35")
    ap.add_argument("--maps", metavar="NAME|DIR", help="train on this map pack (default: the built-in pack)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--init", help="start a new run from this model (an older input layout is upgraded)")
    ap.add_argument("--pool", type=int, default=8, help="frozen older models kept for 'past' partners")
    ap.add_argument("--pool-every", type=int, default=500, help="add the current model to the pool every N iters")
    a = ap.parse_args()
    stages = tuple(int(s) for s in a.stages.split("-")) if "-" in a.stages else (int(a.stages),) * 2

    os.makedirs(a.run, exist_ok=True)
    venv = VecEnv(a.workers, a.envs_per_worker, a.seed, stages, a.mp_start, a.maps)

    import torch  # after the fork
    from model import Net, arch_of, upgrade
    torch.set_num_threads(a.threads)
    torch.manual_seed(a.seed)
    if a.device == "auto":
        a.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    dev = torch.device(a.device)
    print("device %s, %d workers x %d worlds" % (dev, a.workers, a.envs_per_worker), flush=True)
    it0, frames0 = 0, 0
    latest = os.path.join(a.run, "latest.pt")
    ck = None
    if a.resume and os.path.exists(latest):
        ck = torch.load(latest, map_location=dev, weights_only=True)
        a.arch = arch_of(ck["model"])
    elif a.init:
        init = torch.load(a.init, map_location="cpu", weights_only=True)["model"]
        a.arch = arch_of(init)
    net = Net(a.arch).to(dev)
    print("network %s, %.2fM weights" % (a.arch, sum(p.numel() for p in net.parameters()) / 1e6), flush=True)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr, eps=1e-5)
    if ck is not None:
        state = upgrade(ck["model"])
        net.load_state_dict(state)
        if state is ck["model"]:
            opt.load_state_dict(ck["opt"])
        else:                               # older input layout: weights upgraded, new optimizer
            print("upgraded the model inputs to %d" % E.N_VEC)
        it0, frames0 = ck["iter"], ck["frames"]
        print("resumed at iter %d, %d frames" % (it0, frames0))
    elif a.init:
        net.load_state_dict(upgrade(init))
        print("new run from %s" % a.init)

    def finite():
        return all(torch.isfinite(p).all() for p in net.parameters())

    def save(path, it, frames):
        if not finite():                    # never write a broken model
            print("not saving %s: weights are not finite" % path, flush=True)
            return
        torch.save(dict(model={k: v.cpu() for k, v in net.state_dict().items()}, opt=opt.state_dict(), iter=it, frames=frames,
                        args=vars(a)), path + ".tmp")
        os.replace(path + ".tmp", path)

    nE, S, T = venv.n, venv.n * 2, a.steps
    G = np.zeros((T, S, E.N_CH, E.GRID, E.GRID), np.uint8)
    VV = np.zeros((T, S, E.N_VEC), np.float32)
    ACT = np.zeros((T, S), np.int64)
    LP = np.zeros((T, S), np.float32)
    VAL = np.zeros((T + 1, S), np.float32)
    R = np.zeros((T, S), np.float32)
    D = np.zeros((T, S), np.float32)
    M = np.zeros((T, S), bool)

    log_path = os.path.join(a.run, "log.csv")
    new_log = not os.path.exists(log_path)
    logf = open(log_path, "a", newline="")
    log = csv.writer(logf)
    if new_log:
        log.writerow(["iter", "frames", "hours", "fps", "episodes", "clear", "hq", "timeout",
                      "p2_kills", "p2_deaths", "p2_ret", "self_ret", "entropy", "pi_loss", "v_loss"])
    recent = collections.deque(maxlen=300)

    bad_iters = 0
    # -- pool of frozen older models: player 1 in "past" episodes
    pool_dir = os.path.join(a.run, "pool")
    os.makedirs(pool_dir, exist_ok=True)
    if not os.listdir(pool_dir):              # seed: saved checkpoints, every 500 iterations
        import glob
        import re
        cks = sorted(glob.glob(os.path.join(a.run, "ckpt_*.pt")))
        cks = [c for c in cks if int(re.findall(r"(\d+)", os.path.basename(c))[0]) % 500 == 0][-a.pool + 1:]
        for c in cks:
            m = torch.load(c, map_location="cpu", weights_only=True)["model"]
            torch.save(m, os.path.join(pool_dir, os.path.basename(c).replace("ckpt", "iter")))
        torch.save({k: v.cpu() for k, v in net.state_dict().items()}, os.path.join(pool_dir, "iter_%05d.pt" % it0))

    def load_pool():
        names = sorted(os.listdir(pool_dir))[-a.pool:]
        return [upgrade(torch.load(os.path.join(pool_dir, n), map_location="cpu", weights_only=True))
                for n in names], names
    pool, pool_names = load_pool()
    print("pool: %s" % ", ".join(pool_names), flush=True)
    pool = [m for m in pool if arch_of(m) == a.arch] or [{k: v.cpu() for k, v in net.state_dict().items()}]
    past_net = Net(a.arch).to(dev)
    past_net.eval()

    grid, vec, mask, past = venv.reset()
    t_start = time.time()
    it, frames = it0, frames0
    stop = []

    def on_ctrl_c(sig, frame):
        stop.append(1)
        try:
            print("\nCtrl-C: stopping after this iteration and saving (Ctrl-C again: quit now, no save)", flush=True)
        except OSError:
            pass
        signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGINT, on_ctrl_c)
    signal.signal(signal.SIGTERM, on_ctrl_c)          # a "kill": also save first
    pid_file = os.path.join(a.run, "train.pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    lr_end = a.lr if a.lr_end is None else a.lr_end
    lr_scale = 1.0                          # made smaller after repeated NaN updates

    def set_lr():
        f = min(1.0, frames / a.lr_frames) if a.lr_frames > 0 else 0.0
        for g in opt.param_groups:
            g["lr"] = (a.lr + (lr_end - a.lr) * f) * lr_scale

    while time.time() - t_start < a.hours * 3600 and not stop:
        t_iter = time.time()
        set_lr()
        # -- rollout
        net.eval()
        past_net.load_state_dict(random.choice(pool))      # one pool model per rollout
        for t in range(T):
            g = grid.reshape(S, E.N_CH, E.GRID, E.GRID)
            v = vec.reshape(S, E.N_VEC)
            with torch.no_grad():
                logits, val = net(torch.from_numpy(g).to(dev), torch.from_numpy(v).to(dev))
                dist = torch.distributions.Categorical(logits=logits)
                act = dist.sample()
                lp = dist.log_prob(act)
                act, lp, val = act.cpu(), lp.cpu(), val.cpu()
                if past.any():                  # player 1 of "past" worlds: the frozen model
                    rows = torch.from_numpy(np.flatnonzero(past) * 2)
                    pl_logits, _ = past_net(torch.from_numpy(g)[rows].to(dev), torch.from_numpy(v)[rows].to(dev))
                    act[rows] = torch.distributions.Categorical(logits=pl_logits / 0.5).sample().cpu()
            G[t], VV[t], M[t] = g, v, mask.reshape(S)
            ACT[t], LP[t], VAL[t] = act.numpy(), lp.numpy(), val.numpy()
            (grid, vec, mask, past), rews, dones, infos = venv.step(act.numpy().reshape(nE, 2))
            R[t] = rews.reshape(S)
            D[t] = np.repeat(dones, 2).astype(np.float32)
            recent.extend(infos)
        with torch.no_grad():
            _, val = net(torch.from_numpy(grid.reshape(S, E.N_CH, E.GRID, E.GRID)).to(dev),
                         torch.from_numpy(vec.reshape(S, E.N_VEC)).to(dev))
        VAL[T] = val.cpu().numpy()
        frames += T * nE * E.FRAME_SKIP
        t_roll = time.time() - t_iter

        # -- GAE
        adv = np.zeros((T, S), np.float32)
        last = np.zeros(S, np.float32)
        for t in reversed(range(T)):
            nd = 1.0 - D[t]
            delta = R[t] + a.gamma * VAL[t + 1] * nd - VAL[t]
            last = delta + a.gamma * a.lam * nd * last
            adv[t] = last
        ret = adv + VAL[:T]

        # -- update (only samples where the policy really controlled a live tank)
        idx = np.flatnonzero(M.reshape(-1))
        bg = torch.from_numpy(G.reshape(T * S, E.N_CH, E.GRID, E.GRID))
        bv = torch.from_numpy(VV.reshape(T * S, E.N_VEC))
        ba = torch.from_numpy(ACT.reshape(-1))
        blp = torch.from_numpy(LP.reshape(-1))
        badv = torch.from_numpy(adv.reshape(-1))
        bret = torch.from_numpy(ret.reshape(-1))
        net.train()
        ents, pls, vls = [], [], []
        # NaN guard (seen once on Apple "mps" at iter 4797): keep a copy, check, roll back.
        backup = (copy.deepcopy(net.state_dict()), copy.deepcopy(opt.state_dict()))
        bad = False
        if os.environ.get("TANK_TEST_NAN") == str(it + 1):    # test hook: break the weights once
            with torch.no_grad():
                next(net.parameters()).fill_(float("nan"))
        for _ in range(a.epochs):
            if bad:
                break
            np.random.shuffle(idx)
            for s in range(0, len(idx), a.minibatch):
                mb = torch.from_numpy(idx[s:s + a.minibatch])
                logits, val = net(bg[mb].to(dev), bv[mb].to(dev))
                if not (torch.isfinite(logits).all() and torch.isfinite(val).all()):
                    bad = True
                    break
                dist = torch.distributions.Categorical(logits=logits)
                lp = dist.log_prob(ba[mb].to(dev))
                ad = badv[mb].to(dev)
                ad = (ad - ad.mean()) / (ad.std() + 1e-8)
                ratio = torch.exp(torch.clamp(lp - blp[mb].to(dev), -20, 20))
                pl = -torch.min(ratio * ad, torch.clamp(ratio, 1 - a.clip, 1 + a.clip) * ad).mean()
                vl = 0.5 * ((val - bret[mb].to(dev)) ** 2).mean()
                ent = dist.entropy().mean()
                loss = pl + 0.5 * vl - a.ent * ent
                if not torch.isfinite(loss):
                    bad = True
                    break
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()
                ents.append(ent.item())
                pls.append(pl.item())
                vls.append(vl.item())
        if bad or not finite():
            net.load_state_dict(backup[0])
            opt.load_state_dict(backup[1])
            bad_iters += 1
            if bad_iters >= 3:              # again and again: smaller steps
                lr_scale *= 0.5
                set_lr()
                bad_iters = 0
            print("it %d: NaN in the update, rolled back (lr %.2g)" % (it + 1, opt.param_groups[0]["lr"]), flush=True)
        else:
            bad_iters = 0
        it += 1

        # -- log
        hours = (time.time() - t_start) / 3600
        fps = T * nE * E.FRAME_SKIP / (time.time() - t_iter)
        if recent:
            rc = list(recent)
            mean = lambda f: float(np.mean([f(x) for x in rc]))  # noqa: E731
            selfp = [x for x in rc if x["mode"] == "self"]
            row = [it, frames, round(hours, 3), int(fps), len(rc), mean(lambda x: x["cleared"]),
                   mean(lambda x: x["hq"]), mean(lambda x: x["timeout"]),
                   mean(lambda x: x["kills"][1]), mean(lambda x: x["deaths"][1]), mean(lambda x: x["ret"][1]),
                   float(np.mean([x["ret"][0] + x["ret"][1] for x in selfp])) if selfp else 0.0]
        else:
            row = [it, frames, round(hours, 3), int(fps), 0] + [0.0] * 7
        row += [float(np.mean(ents)) if ents else 0.0, float(np.mean(pls)) if pls else 0.0,
                float(np.mean(vls)) if vls else 0.0]
        log.writerow([round(x, 4) if isinstance(x, float) else x for x in row])
        logf.flush()
        print("it %4d  %6.1fM frames  %5d fps (roll %.1fs)  eps %3d  clear %.2f  hq %.2f  timeout %.2f  "
              "p2 kills %.1f deaths %.1f ret %.1f  ent %.2f  lr %.2g" % (
                  it, frames / 1e6, fps, t_roll, row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[12],
                  opt.param_groups[0]["lr"]),
              flush=True)
        if it % 10 == 0:
            save(latest, it, frames)
        if it % 100 == 0:
            save(os.path.join(a.run, "ckpt_%05d.pt" % it), it, frames)
        if it % a.pool_every == 0 and finite():         # add the current model to the pool
            torch.save({k: v.cpu() for k, v in net.state_dict().items()}, os.path.join(pool_dir, "iter_%05d.pt" % it))
            for n in sorted(os.listdir(pool_dir))[:-a.pool]:
                os.remove(os.path.join(pool_dir, n))
            pool, pool_names = load_pool()
    save(latest, it, frames)
    print("saved %s (iter %d)" % (latest, it), flush=True)
    venv.close()
    try:
        os.remove(pid_file)
    except OSError:
        pass
    print("done: %d iters, %.1fM frames" % (it, frames / 1e6))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)                         # do not hang in exit (seen on macOS after a crash)
