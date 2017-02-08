#!/usr/bin/env python3
import os
import subprocess
import tempfile
import tarfile
import lzma
import sys
import traceback

from nixipfs.karkinos import *
from nixipfs.hydra_helpers import *
from nixipfs.download_helpers import *
from nixipfs.utils import ccd

# This is very close to that what the NixOS release script does.
# A general approach to release an arbitrary jobset is still missing but it should be
# easier to extend now with the Karkinos class and helper functions
def create_channel_release(channel, hydra, project, jobset, cache, outdir, tmpdir, target_cache=None):
    release_info = ReleaseInfo(fetch_release_info(hydra, project, jobset))
    k = Karkinos(hydra, release_info.eval_id)
    eval_info = EvalInfo(k.fetch_eval_info())
    store_paths = k.fetch_store_paths()
    files_cache = os.path.join(outdir, "nixos-files.sqlite")

    out_dir = os.path.abspath(os.path.join(outdir, channel, release_info.name))
    tmp_dir = os.path.abspath(tmpdir)
    assert(os.path.isdir(tmp_dir))

    if os.path.isfile(os.path.join(out_dir, 'git-revision')):
        return out_dir

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "src-url"), "w") as f:
        f.write(k.eval_url)

    if target_cache == None:
        with open(os.path.join(out_dir, "binary-cache-url"), "w") as f:
            f.write(cache)
    else:
        with open(os.path.join(out_dir, "binary-cache-url"), "w") as f:
            f.write(target_cache)

    with open(os.path.join(out_dir, 'store-paths'), 'w') as f:
        f.write("\n".join(set(store_paths)))

    with lzma.open(os.path.join(out_dir, 'store-paths.xz'), 'w') as f:
        f.write("\n".join(set(store_paths)).encode('utf-8'))

    if channel.startswith('nixos'):
        k.download_file('nixos.channel', out_dir, 'nixexprs.tar.xz', tmp_dir=tmp_dir)
        k.download_file('nixos.iso_minimal.x86_64-linux', out_dir, tmp_dir=tmp_dir)
        if not channel.endswith('-small'):
            k.download_file('nixos.iso_minimal.i686-linux', out_dir, tmp_dir=tmp_dir)
            k.download_file('nixos.iso_graphical.x86_64-linux', out_dir, tmp_dir=tmp_dir)
            k.download_file('nixos.ova.x86_64-linux', out_dir, tmp_dir=tmp_dir)
    else:
        k.download_file('tarball', out_dir, 'nixexprs.tar.gz', tmp_dir=tmp_dir)

    if channel.startswith('nixos'):
        nixexpr_tar = os.path.join(out_dir, 'nixexprs.tar.xz')
        with tarfile.open(nixexpr_tar, "r:xz") as nixexpr:
            if any([s for s in nixexpr.getnames() if 'programs.sqlite' in s]):
                contains_programs = True
            else:
                contains_programs = False

        if not contains_programs:
            with tempfile.TemporaryDirectory() as temp_dir:
                nixexpr = tarfile.open(nixexpr_tar, 'r:xz')
                nixexpr.extractall(temp_dir)
                nixexpr.close()

                expr_dir = os.path.join(temp_dir, os.listdir(temp_dir)[0])
                try:
                    subprocess.run('generate-programs-index {} {} {} {} {}'.format(
                                    files_cache,
                                    os.path.join(expr_dir, 'programs.sqlite'),
                                    cache,
                                    os.path.join(out_dir, 'store-paths'),
                                    os.path.join(expr_dir,'nixpkgs')),
                                    shell=True, check=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except(subprocess.CalledProcessError):
                    raise Exception("Could not execute {}".format("generate-programs-index"))
                os.remove(os.path.join(expr_dir, 'programs.sqlite-journal'))
                os.remove(nixexpr_tar)
                nixexpr = tarfile.open(nixexpr_tar, 'w:xz')
                with ccd(temp_dir):
                    nixexpr.add(os.listdir()[0])
                nixexpr.close()

    with open(os.path.join(out_dir, "git-revision"), "w") as f:
        f.write(eval_info.git_rev)
    return out_dir
