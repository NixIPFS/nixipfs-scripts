{ pkgs ? (import ./../pkgs.nix), nix ? pkgs.nixUnstable }:
with pkgs;
stdenv.mkDerivation {
  name = "generate-programs-index";
  buildInputs = [ sqlite nlohmann_json nix ];
  buildCommand = ''
    mkdir -p $out/bin
    g++ -g ${./generate-programs-index.cc} -Wall -std=c++11 -o $out/bin/generate-programs-index \
      -I ${nix.dev}/include/nix -lnixmain -lnixexpr -lnixformat -lsqlite3 -lgc -I .
  '';
}
