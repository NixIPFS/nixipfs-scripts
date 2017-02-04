NixIPFS Release Scripts
======================
![banner](https://ipfs.io/ipfs/QmRmG2W1DJZs4pKq6tz4ofeyrn9vgA2tAe11CjMRm4TPpA/nixipfs_184x160.gif)

This is a collection of scripts that fetch jobsets from a Hydra, create releases and
publish them to IPFS.
This is a working solution for NAR distribution but should be rewritten completely for
an IPLD approach.

Usage
-----

Start IPFS on your host or have the API close (latency) to you:

```
release_nixos --dir /data/nixipfs --tmpdir /data/tmp --ipfsapi 127.0.0.1 5001 --config nixos_release.json
```

This downloads the latest release builds of NixOS and all .narinfo + .nar files 
that belong to the runtime closure (if all store-paths are resolved) to `--dir`.
`tmpdir` will be used for `.nar/.tar` extraction since `/tmp` is often too small

* `--print_only` will not add anything to IPFS and will not download the *.nar 
files locally.
Instead the paths are printed and can be piped to a file so you can fetch them 
using another tool / on another host.
* `--gc` the scripts ship their own garbage collector that purges the global binary
cache of all files that are not used by a release.
* `--no_ipfs` will not add anything to IPFS
* `--config` points to a json file that contains most of the parameters (see nixos_release.json for an example)

The modules used by release_nixos have their own scripts that can be used from a
CLI.

* `create_channel_release` fetches the latest tested build of a single jobset in
  a project and creates a channel
* `update_binary_cache` updates a global binary cache with the runtime closure of
  a release
* `garbage_collect` deletes all unreferenced files from a global binary cache.
* `create_nixipfs` creates a IPFS directory from a local directory

Caching
-------

In order to reduce the requests to the IPFS API, the hashes of each directory is stored on disk.
If you want to re-add a directory with changed content (e.g. `binary-cache-url`) you need to delete
a file called `ipfs_hash` in the same directory.

Run this in the `releases` path to add all releases again:
```
find . -iname ipfs_hash | xargs rm
```

License
-------

* `/nixipfs/*` is released under the GPLv3, see COPYING
* `/generate_programs_index/*` has no license yet (Copyright by Eelco Dolstra, LGPL assumed)
