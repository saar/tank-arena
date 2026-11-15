"""Installed map packs and saved settings.

Installed packs live in the user data folder, so they stay after an update of the game:
    Linux    ~/.local/share/tank-arena/maps/<name>/     ($XDG_DATA_HOME if set)
    macOS    ~/Library/Application Support/tank-arena/maps/<name>/
    Windows  %APPDATA%\\tank-arena\\maps\\<name>\\
The pack chosen on the title screen is saved in settings.json in the same folder.
"""
import json
import os
import shutil
import sys

from maps import DEFAULT_PACK, MapPack

DEFAULT_NAME = "default"


def data_dir():
    if os.environ.get("TANK_ARENA_HOME"):                  # tests or a portable install
        return os.environ["TANK_ARENA_HOME"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "tank-arena")


def maps_dir():
    return os.path.join(data_dir(), "maps")


def available():
    """{name: folder}: the built-in pack first, then the installed packs (sorted)."""
    out = {DEFAULT_NAME: DEFAULT_PACK}
    d = maps_dir()
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            if os.path.isdir(os.path.join(d, n)) and n != DEFAULT_NAME:
                out[n] = os.path.join(d, n)
    return out


def resolve(name_or_path):
    """A pack name (installed) or a folder path -> folder. None -> the saved choice."""
    if name_or_path is None:
        name_or_path = load_settings().get("maps", DEFAULT_NAME)
    packs = available()
    if name_or_path in packs:
        return packs[name_or_path]
    if os.path.isdir(name_or_path):
        return name_or_path
    print("map pack %r not found, using the default pack" % name_or_path)
    return DEFAULT_PACK


def install(src, name=None):
    """Check a pack folder and copy it into the data folder. Returns the name."""
    pack = MapPack(src)                        # raises MapError if a file is bad
    name = name or os.path.basename(os.path.normpath(src))
    if not name or name == DEFAULT_NAME or os.sep in name:
        raise ValueError("choose another name for the pack: --name NAME")
    dst = os.path.join(maps_dir(), name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for f in os.listdir(src):
        if f.endswith(".txt"):
            shutil.copy2(os.path.join(src, f), dst)
    print("installed map pack %r (%d stages) in %s" % (name, pack.count, dst))
    return name


def remove(name):
    dst = os.path.join(maps_dir(), name)
    if name == DEFAULT_NAME or not os.path.isdir(dst):
        raise ValueError("no installed map pack named %r" % name)
    shutil.rmtree(dst)
    if load_settings().get("maps") == name:
        save_settings(maps=DEFAULT_NAME)
    print("removed map pack %r" % name)


def settings_path():
    return os.path.join(data_dir(), "settings.json")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(**kv):
    s = load_settings()
    s.update(kv)
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1)
    except OSError as e:
        print("could not save settings:", e)
