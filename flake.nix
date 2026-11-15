{
  description = "Tank Arena: a top-down tank game with an AI partner";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
      # pygbag: packs the game for the browser (tools/web_build.sh); not in nixpkgs
      pygbag = py: py.pkgs.buildPythonPackage rec {
        pname = "pygbag";
        version = "0.9.3";
        format = "wheel";
        src = py.pkgs.fetchPypi {
          inherit pname version format;
          dist = "py3"; python = "py3";
          sha256 = "ada203ff5a214f721029cb3b3741f641b032cde1ccaac60bc8dd9e641f3da3d5";
        };
        doCheck = false;
      };
    in {
      devShells = forAll (pkgs: {
        # game + tools; numpy and torch are for the AI partner (ml/)
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (p: [ p.pygame-ce p.pillow p.numpy p.torch (pygbag pkgs.python3) ]))
            pkgs.gh            # GitHub CLI: releases (the AI model)
          ] ++ pkgs.lib.optionals pkgs.stdenv.hostPlatform.isLinux [
            pkgs.podman        # container image: ./container.sh (docs/CONTAINER.md)
            pkgs.actionlint    # checks .github/workflows/*.yml
          ];
        };
      });
    };
}
