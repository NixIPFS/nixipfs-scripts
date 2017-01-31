#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import queue
import threading
import urllib

from nixipfs.nix_helpers import *
from nixipfs.download_helpers import *
from nixipfs.defaults import *

def download_worker(binary_cache):
    global nar_queue
    while True:
        work = nar_queue.get()
        if work is None:
            break
        for x in range(0, DEFAULT_DOWNLOAD_TRIES):
            holdoff = DEFAULT_HTTP_ERROR_SLEEP*x
            # work is a list consisting of [path, destination, hash]
            try:
                download_file_from_cache(work[0], work[1], binary_cache)
            except urllib.error.ContentTooShortError:
                print("Could not download {} Retrying in {} s".format(work[0], holdoff))
                time.sleep(holdoff)
            except (urllib.error.HTTPError, urllib.error.URLError):
                print("Could not download {} Retrying in {} s".format(work[0], holdoff))
                time.sleep(holdoff)

            if os.path.isfile(work[1]):
                h_res = subprocess.run("nix hash-file --base32 --type {} {}".format(work[2].split(':')[0], work[1]), shell=True, stdout=subprocess.PIPE)
                if h_res.stdout.decode('utf-8').strip() == work[2].split(':')[1].strip():
                    break
                else:
                    os.unlink(work[1])
        if not os.path.isfile(work[1]):
            print("Giving up on {}".format(work[1]))

        nar_queue.task_done()

def narinfo_worker(cache, local_cache):
    global nic
    while True:
        work = nic.get_work()
        if work is None:
            break
        for x in range(0, DEFAULT_DOWNLOAD_TRIES):
            try:
                narinfo = fetch_file_from_cache(work, cache, local_cache)
            except (urllib.error.ContentTooShortError, urllib.error.HTTPError, urllib.error.URLError):
                print("Could not fetch {}. Retrying in {} s".format(work[0], DEFAULT_HTTP_ERROR_SLEEP))
                time.sleep(DEFAULT_HTTP_ERROR_SLEEP)
            if len(narinfo):
                break
        nic.turn_in(work, narinfo)

def update_binary_cache(cache, release, outdir, concurrent=DEFAULT_CONCURRENT_DOWNLOADS, print_only=False, cache_info=None):
    global nar_queue
    global nic
    binary_cache_path = os.path.join(outdir, 'binary_cache')
    linked_cache_path = os.path.join(release, 'binary_cache')
    assert(os.path.isdir(release))
    os.makedirs(os.path.join(binary_cache_path, 'nar'), exist_ok=True)
    os.makedirs(os.path.join(linked_cache_path, 'nar'), exist_ok=True)

    with open(os.path.join(release, 'store-paths'), 'r') as f:
        store_paths = f.read()

    threads = []
    nic = NarInfoCollector()
    nic.start(store_paths.split('\n'))
    for i in range(concurrent):
        t = threading.Thread(target=narinfo_worker, args=(cache, binary_cache_path))
        threads.append(t)
        t.start()
    nic.queue.join()
    for i in range(concurrent):
        nic.queue.put(None)
    for t in threads:
        t.join()
    threads = []

    # Write NarInfo files
    for ni in nic.collection:
        with open(os.path.join(binary_cache_path, ni[0]), 'w') as f:
            f.write(ni[1].to_string())
    # Figure out all nars and the fileHash that we want to fetch
    nars = { ni[1].d['URL'] : ni[1].d['FileHash'] for ni in nic.collection }

    if print_only:
        for nar, filehash in nars.items():
            print("{},{}".format(nar, filehash))
    else:
        nar_queue = queue.Queue()
        for i in range(concurrent):
            t = threading.Thread(target=download_worker, args=(cache, ))
            threads.append(t)
            t.start()
        for url, file_hash in nars.items():
            nar_location_disk = os.path.join(binary_cache_path, url)
            if not os.path.isfile(nar_location_disk):
                nar_queue.put([url, nar_location_disk, file_hash])
        nar_queue.join()
        for i in range(concurrent):
            nar_queue.put(None)
        for t in threads:
            t.join()
        # All nars/narinfos have been written, link to them
        with ccd(linked_cache_path):
            for ni in nic.collection:
                # Produces xyz.narinfo -> ../../binary_cache/xyz.narinfo
                target = os.path.join(binary_cache_path, ni[0])
                assert(os.path.isfile(target))
                if not os.path.isfile(os.path.basename(ni[0])):
                    os.symlink(os.path.relpath(target), ni[0])
        with ccd(os.path.join(linked_cache_path, 'nar')):
            for nar, file_hash in nars.items():
                target = os.path.join(binary_cache_path, 'nar', os.path.basename(nar))
                assert(os.path.isfile(target))
                if not os.path.isfile(os.path.basename(nar)):
                    os.symlink(os.path.relpath(target), os.path.basename(nar))
        if cache_info is not None:
            nci = NarInfo()
            nci.d = cache_info
            with open(os.path.join(linked_cache_path, 'nix-cache-info'), 'w') as f:
                f.write(nci.to_string())
