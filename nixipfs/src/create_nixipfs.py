#!/usr/bin/env python3
import os
import ipfsapi
import contextlib
import hashlib
import time
from glob import glob

from nixipfs.nix_helpers import *

RELEASE_VALID_PATHS=['binary-cache-url', 'git-revision', 'nixexpr.tar.xz', '.iso', 'src-url', 'store-paths.xz']
# ADD_OPTIONS={'raw-leaves': 'true'}
ADD_OPTIONS={'pin':'false'}
FILES_OPTIONS={'flush': 'false'}

# TODO: upstream this to ipfsapi
def files_flush(api, path, **kwargs):
    args = (path,)
    return api._client.request('/files/flush', args=args, **kwargs)

def add_binary_cache(api, local_dir, mfs_dir, hash_cache):
    binary_cache_dir = os.path.join(local_dir, 'binary_cache')
    nar_dir = os.path.join(binary_cache_dir, 'nar')

    mfs_binary_cache_dir = os.path.join(mfs_dir, 'binary_cache')
    mfs_nar_dir = os.path.join(mfs_binary_cache_dir, 'nar')

    api.files_mkdir(mfs_binary_cache_dir)
    api.files_mkdir(mfs_nar_dir)

    nar_files = [ e for e in os.listdir(nar_dir) if '.nar' in e ]
    for idx, nar in enumerate(nar_files):
        if hash_cache.get(nar) is None:
            nar_path = os.path.join(nar_dir, nar)
            hash_cache.update({ nar : api.add(nar_path, recursive=False, opts=ADD_OPTIONS)['Hash']})
    for idx, nar in enumerate(sorted(nar_files)):
        print("files cp {}/{}".format(idx+1, len(nar_files)))
        api.files_cp("/ipfs/" + hash_cache[nar], os.path.join(mfs_nar_dir, nar), opts=FILES_OPTIONS)

    if os.path.isfile(os.path.join(binary_cache_dir, 'nix-cache-info')):
        api.files_cp("/ipfs/" + api.add(os.path.join(binary_cache_dir, 'nix-cache-info'), opts=ADD_OPTIONS)['Hash'],
                                        os.path.join(mfs_binary_cache_dir, 'nix-cache-info'), opts=FILES_OPTIONS)

    narinfo_files = [ e for e in os.listdir(binary_cache_dir) if e.endswith('.narinfo') ]
    for idx, nip in enumerate(narinfo_files):
        ni_hash = hash_cache.get(nip)
        if ni_hash is None:
            with open(os.path.join(binary_cache_dir, nip), 'r') as f:
                ni = NarInfo(f.read())
            ni.d['IPFSHash'] = hash_cache[ni.d['URL'].split('/')[1]]
            with open(os.path.join(binary_cache_dir, nip), 'w') as f:
                f.write("\n".join(ni.dump()+['']))
            ni_hash = api.add(os.path.join(binary_cache_dir, nip), recursive=False, opts=ADD_OPTIONS)['Hash']
            hash_cache.update({nip : ni_hash})
    for idx, nip in enumerate(sorted(narinfo_files)):
        print("cp {}/{}".format(idx+1, len(narinfo_files)))
        api.files_cp("/ipfs/" + hash_cache[nip], os.path.join(mfs_binary_cache_dir, nip), opts=FILES_OPTIONS)
    files_flush(api, mfs_binary_cache_dir)
    return api.files_stat(mfs_binary_cache_dir)['Hash']

def add_nixos_release(api, local_dir, mfs_dir, hash_cache):
    # if the directory has been added to IPFS once, reuse that hash
    hash_file = os.path.join(local_dir, "ipfs_hash")
    if os.path.isfile(hash_file):
        api.files_mkdir(os.path.dirname(mfs_dir), parents=True)
        with open(hash_file, 'r') as f:
            api.files_cp("/ipfs/" + f.read().strip(), mfs_dir, opts=FILES_OPTIONS)
    else:
        api.files_mkdir(mfs_dir, parents=True)
        file_hashes = {}
        for f in [ x for x in os.listdir(local_dir) if [ y for y in RELEASE_VALID_PATHS if y in x ]]:
            file_path = os.path.join(local_dir, f)
            if hash_cache.get(f) is not None:
                file_hashes.update({ f : hash_cache[f] })
            else:
                h = api.add(file_path, recursive=False, opts=ADD_OPTIONS)['Hash'] 
                file_hashes.update({ f : h})
                if f.endswith(".iso") or f.endswith(".ova"):
                    hash_cache.update({f : h})
        for name, obj in file_hashes.items():
            api.files_cp("/ipfs/" + obj, os.path.join(mfs_dir, name), opts=FILES_OPTIONS)
        add_binary_cache(api, local_dir, mfs_dir, hash_cache)
        with open(hash_file, 'w') as f:
            f.write(api.files_stat(mfs_dir)['Hash'].strip())
    files_flush(api, mfs_dir)

def create_nixipfs(local_dir, ipfs_api):
    api = ipfsapi.connect(ipfs_api[0], ipfs_api[1])
    hash_cache = {}
    hash_cache_file = os.path.join(local_dir, 'ipfs_hashes')
    nixfs_dir = '{}_{}'.format('/nixfs', int(time.time()))
    channels_dir = os.path.join(local_dir, 'channels')
    releases_dir = os.path.join(local_dir, 'releases')

    if os.path.isfile(hash_cache_file):
        with open(hash_cache_file, 'r') as f:
            hash_cache.update(dict([ [e.split(':')[0].strip(),
                                      e.split(':')[1].strip() ] for e in f.readlines() ]))
    api.files_mkdir(nixfs_dir)

    # Add global binary cache
    print('adding global cache...')
    add_binary_cache(api, local_dir, nixfs_dir, hash_cache)

    # Add all releases
    for release_name in [ e.rstrip('/') for e in glob(releases_dir + '/*/')]:
        for release_dir in [ e.rstrip('/') for e in glob(release_name + '/*/')]:
            print('adding release...')
            add_nixos_release(api, release_dir, os.path.join(nixfs_dir, 'releases', os.path.basename(release_name), os.path.basename(release_dir)), hash_cache)
    # Add all channels
    for channel_dir in [ e.rstrip('/') for e in glob(channels_dir + '/*/')]:
        print('adding channel/release...')
        add_nixos_release(api, channel_dir, os.path.join(nixfs_dir, 'channels', os.path.basename(channel_dir)), hash_cache)

    nixfs_hash = api.files_stat(nixfs_dir)['Hash']
    print('flushing...')
    files_flush(api, nixfs_dir)
    print('nixfs_hash: ' + nixfs_hash)
    print('pinning...')
    api.pin_add(nixfs_hash)
    with open(hash_cache_file, 'w') as f:
        f.write("\n".join([ "{}:{}".format(k,v) for k,v in hash_cache.items() ]))
