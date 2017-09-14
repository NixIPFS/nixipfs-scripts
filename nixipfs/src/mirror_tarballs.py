import json
import urllib.request
import os
import queue
import tempfile
import subprocess
import threading
from pygit2 import clone_repository, GIT_RESET_HARD
from shutil import copyfile

from nixipfs.download_helpers import DownloadFailed
from nixipfs.nix_helpers import nix_hash
from nixipfs.utils       import ccd
from nixipfs.defaults    import *

# For testing purposes:
#NIX_EXPR = '(import <nixpkgs> {}).hello'
NIX_EXPR = 'builtins.removeAttrs ((import pkgs/top-level/release.nix { scrubJobs = false; supportedSystems = [ "x86_64-linux" "x86_64-darwin" ]; })) ["unstable" "tarball" "darwin-unstable" ]'
NIX_INSTANTIATE_CMD = "nix-instantiate --eval --json --strict maintainers/scripts/find-tarballs.nix --arg expr '{}'".format(NIX_EXPR)

MAIN_ALGO = "sha512"
MAIN_BASE = "base16"

VALID_URL_SCHEMES = [ "http:", "https:", "ftp:", "mirror:" ]

failed_entries_l = threading.Lock()
failed_entries = []

def create_mirror_dirs(target_dir, revision):
    md5_path = os.path.join(target_dir, "md5")
    sha1_path = os.path.join(target_dir, "sha1")
    sha256_path = os.path.join(target_dir, "sha256")
    sha512_path = os.path.join(target_dir, "sha512")
    name_path = os.path.join(target_dir, "by-name")
    revision_path = os.path.join(target_dir, "revisions", revision)
    os.makedirs(md5_path, exist_ok=True)
    os.makedirs(sha1_path, exist_ok=True)
    os.makedirs(sha256_path, exist_ok=True)
    os.makedirs(sha512_path, exist_ok=True)
    os.makedirs(name_path, exist_ok=True)
    os.makedirs(revision_path, exist_ok=True)

def check_presence(target_dir, value):
    paths = [
        os.path.join(target_dir, "md5", value),
        os.path.join(target_dir, "sha1", value),
        os.path.join(target_dir, "sha256", value),
        os.path.join(target_dir, "sha512", value),
        os.path.join(target_dir, "by-name", value)
    ]
    return [ path for path in paths if os.path.exists(path) ]

def mirror_file(target_dir, path, name, revision):
    make_path = lambda x: os.path.join(target_dir, x)

    md5_16 = nix_hash(path, hash_type="md5", base="base16")
    sha1_16 = nix_hash(path, hash_type="sha1", base="base16")
    sha256_16 = nix_hash(path, hash_type="sha256", base="base16")
    sha256_32 = nix_hash(path, hash_type="sha256", base="base32")
    sha512_16 = nix_hash(path, hash_type="sha256", base="base16")
    sha512_32 = nix_hash(path, hash_type="sha256", base="base32")

    main_file = make_path("sha512/{}".format(sha512_16))

    copyfile(path, main_file)
    with ccd(os.path.join(target_dir, "md5")):
        if not os.path.exists(md5_16):
            os.symlink(os.path.relpath(main_file), md5_16)
    with ccd(os.path.join(target_dir, "sha1")):
        if not os.path.exists(sha1_16):
            os.symlink(os.path.relpath(main_file), sha1_16)
    with ccd(os.path.join(target_dir, "sha256")):
        if not os.path.exists(sha256_16):
            os.symlink(os.path.relpath(main_file), sha256_16)
        if not os.path.exists(sha256_32):
            os.symlink(os.path.relpath(main_file), sha256_32)
    with ccd(os.path.join(target_dir, "sha512")):
        if not os.path.exists(sha512_32):
            os.symlink(os.path.relpath(main_file), sha512_32)
    with ccd(os.path.join(target_dir, "by-name")):
        if not os.path.exists(name):
            os.symlink(os.path.relpath(main_file), name)
    with ccd(os.path.join(target_dir, "revisions", revision)):
        if not os.path.exists(sha512_16):
            os.symlink(os.path.relpath(main_file), sha512_16)

def download_worker(target_dir, revision):
    global download_queue
    while True:
        work = download_queue.get()
        if work is None:
            break
        try:
            res = nix_prefetch_url(work['url'], work['hash'], work['type'])
            mirror_file(target_dir, res['path'], work['name'], revision)
            nix_store_delete(res['path'])
        except DownloadFailed:
            append_failed_entry(work)
        download_queue.task_done()

def append_failed_entry(entry):
    failed_entries_l.acquire()
    failed_entries.append(entry)
    failed_entries_l.release()

def nix_prefetch_url(url, hashv, hash_type="sha256"):
    assert(hash_type in [ "md5", "sha1", "sha256", "sha512" ])
    # For some reason, nix-prefetch-url stalls, the timeout kills the process
    # after 15 minutes, this should be enough for all downloads
    try:
        res = subprocess.run("nix-prefetch-url --print-path --type {} {} {}".format(hash_type, url, hashv), shell=True, stdout=subprocess.PIPE, timeout=900)
    except subprocess.TimeoutExpired:
        raise DownloadFailed
    if res.returncode != 0:
        raise DownloadFailed
    lines = res.stdout.decode('utf-8').split('\n')
    r = {}
    r['hash'] = lines[0].strip()
    r['path'] = lines[1].strip()
    return r

def nix_store_delete(path):
    res = subprocess.run("nix-store --delete {}".format(path), shell=True, stdout=subprocess.PIPE)
    return res.returncode

def mirror_tarballs(target_dir, git_repo, git_revision, concurrent=DEFAULT_CONCURRENT_DOWNLOADS):
    global failed_entries
    global download_queue
    create_mirror_dirs(target_dir, git_revision)
    download_queue = queue.Queue()
    threads = []
    with tempfile.TemporaryDirectory() as temp_dir:
        repo = clone_repository(git_repo, temp_dir)
        repo.reset(git_revision, GIT_RESET_HARD)
        with ccd(repo.workdir):
            res = subprocess.run(NIX_INSTANTIATE_CMD, shell=True, stdout=subprocess.PIPE)
            output = json.loads(res.stdout.decode('utf-8').strip())
    #    with open(os.path.join(target_dir, "tars.json"), "w") as f:
    #        f.write(json.dumps(output))
    #with open(os.path.join(target_dir, "tars.json"), "r") as f:
    #    output = json.loads(f.read())
    for idx, entry in enumerate(output):
        if not (len( [ x for x in VALID_URL_SCHEMES if entry['url'].startswith(x) ]) == 1):
            append_failed_entry(entry)
            print("url {} is not in the supported url schemes.".format(entry['url']))
            continue
        elif (len(check_presence(target_dir, entry['hash'])) or
              len(check_presence(target_dir, entry['name']))):
            print("url {} already mirrored".format(entry['url']))
            continue
        else:
            download_queue.put(entry)
    for i in range(concurrent):
        t = threading.Thread(target=download_worker, args=(target_dir, git_revision, ))
        threads.append(t)
        t.start()
    download_queue.join()
    for i in range(concurrent):
        download_queue.put(None)
    for t in threads:
        t.join()
    log = "########################\n"
    log += "SUMMARY OF FAILED FILES:\n"
    log += "########################\n"
    for entry in failed_entries:
        log += "url:{}, name:{}\n".format(entry['url'], entry['name'])
    with open(os.path.join(target_dir, "revisions", git_revision, "log"), "w") as f:
        f.write(log)
    return log
