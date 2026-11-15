{
  description = "Tank Arena: a top-down tank game with an AI partner";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in {
      devShells = forAll (pkgs: {
        # game + tools; numpy and torch are for the AI partner (ml/)
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (p: [ p.pygame-ce p.pillow p.numpy p.torch ]))
            pkgs.gh            # GitHub CLI: releases (the AI model)
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pkgs.podman        # container image: ./container.sh (docs/CONTAINER.md)
          ];
        };
      });
    };
}
