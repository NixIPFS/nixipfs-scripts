{ pkgs ? (import ./pkgs.nix){} }:

rec {
  generate_programs_index = import ./generate_programs_index/default.nix { inherit pkgs; };
  nixipfs = import ./nixipfs/default.nix { inherit pkgs generate_programs_index; };
  nixipfsEnv = pkgs.stdenv.mkDerivation rec {
    name = "nixipfs-env";
    version = "0.0.0.1";
    src = ./.;
    buildInputs = [ nixipfs ];
  };
}
