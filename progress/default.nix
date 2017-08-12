{ stdenv, pkgs, fetchurl, pythonPackages }:

pythonPackages.buildPythonPackage rec {
  name = "progress-${version}";
  version = "1.3";
  src = fetchurl {
    url = "mirror://pypi/p/progress/${name}.tar.gz";
    sha256 = "02pnlh96ixf53mzxr5lgp451qg6b7ff4sl5mp2h1cryh7gp8k3f8";
  };

}
