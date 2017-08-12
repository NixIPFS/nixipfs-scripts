{ pkgs ? (import ./../pkgs.nix),
  generate_programs_index ? (import ./../generate_programs_index {}),
  pythonPackages,
  progress
}:
with pkgs;

pythonPackages.buildPythonPackage rec {
  name = "nixipfs-${version}";
  version = "0.4.0";
  src = ./.;
  propagatedBuildInputs = with pythonPackages; [
    python
    ipfsapi
    jsonschema
    nixUnstable
    generate_programs_index
    progress
  ];
}
