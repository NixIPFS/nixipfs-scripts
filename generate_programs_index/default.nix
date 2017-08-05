{ pkgs ? (import ./../pkgs.nix), nix ? pkgs.nixUnstable }:
with pkgs;
stdenv.mkDerivation {
  name = "generate-programs-index";
  buildInputs = [ pkgconfig sqlite nlohmann_json nix ];
  buildCommand = ''
    mkdir -p $out/bin
    cp ${./file-cache.hh} file-cache.hh
    g++ -g ${./generate-programs-index.cc} -I . -Wall -std=c++14 -o $out/bin/generate-programs-index \
      $(pkg-config --cflags nix-main) \
      $(pkg-config --libs nix-main) \
      $(pkg-config --libs nix-expr) \
      $(pkg-config --libs nix-store) \
      -lsqlite3 -lgc
  '';
}
