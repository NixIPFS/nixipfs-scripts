{ pkgs ? (import ./pkgs.nix){} }:

rec {
  nixpkgs.config.packageOverrides = pkgs: {
    # fix nix release for generate_package_index
    # nixpkgs @ e0a848fb16244109f700f28bfb1b32c13be3d465
    nixUnstable = pkgs.nixUnstable.overrideDerivation (oldAttrs: {
      suffix = "pre5511_c94f3d55";
      src = pkgs.fetchFromGitHub {
        owner = "NixOS";
        repo = "nix";
        rev = "c94f3d5575d7af5403274d1e9e2f3c9d72989751";
        sha256 = "1akfzzm4f07wj6l7za916xv5rnh71pk3vl8dphgradjfqb37bv18";
      };
    });
  };

  generate_programs_index = import ./generate_programs_index/default.nix { inherit pkgs; };
  nixipfs = import ./nixipfs/default.nix { inherit pkgs generate_programs_index; };
  nixipfsEnv = pkgs.stdenv.mkDerivation rec {
    name = "nixipfs-env";
    version = "0.0.0.1";
    src = ./.;
    buildInputs = [ nixipfs ];
  };
}
