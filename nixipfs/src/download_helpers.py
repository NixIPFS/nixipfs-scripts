import json
import urllib.request
import tempfile
import os
import tarfile
import lzma
import bz2
import subprocess
import queue
import threading
import time
from shutil import copyfile

from nixipfs.nix_helpers import nar_info_from_path, NarInfo
from nixipfs.utils import ccd
from nixipfs.defaults import *

class DownloadFailed(Exception):
    pass

def fetch_json(url):
    req = urllib.request.Request(url, headers = { "Content-Type" : "application/json",
                                                  "Accept" : "application/json" })
    return json.loads(urllib.request.urlopen(req).read().decode('utf8'))

def fetch_file_from_cache(path, binary_cache = DEFAULT_BINARY_CACHE_URL, local_cache = None, force = False, tries = DEFAULT_DOWNLOAD_TRIES):
    res = ""
    if not (local_cache == None and force == False):
        local_path = os.path.join(local_cache, path)
        if os.path.isfile(local_path):
            with open(local_path, "r") as f:
                res = f.read()
    if not len(res):
        url = "{}/{}".format(binary_cache, path)
        for x in range(0, tries):
            try:
                req = urllib.request.Request(url)
                res = urllib.request.urlopen(url).read().decode('utf8')
                if len(res):
                    break
            except (urllib.error.ContentTooShortError, urllib.error.HTTPError, urllib.error.URLError):
                time.sleep(DEFAULT_HTTP_ERROR_SLEEP)
    return res

def download_file_from_cache(path, dest, binary_cache = DEFAULT_BINARY_CACHE_URL, tries = DEFAULT_DOWNLOAD_TRIES):
    url = "{}/{}".format(binary_cache, path)

    for x in range(0, tries):
        holdoff = DEFAULT_HTTP_ERROR_SLEEP*x
        try:
            urllib.request.urlretrieve(url, dest)
            return
        except (urllib.error.ContentTooShortError, urllib.error.HTTPError, urllib.error.URLError):
            time.sleep(holdoff)
    # Only reached if download failed
    raise DownloadFailed("Failed to download {}".format(path))

def fetch_release_info(hydra_url, project, jobset, job):
    url = "{}/job/{}/{}/{}/latest-finished".format(hydra_url, project, jobset, job)
    return fetch_json(url)

def fetch_store_path(path, dest_file, binary_cache = DEFAULT_BINARY_CACHE_URL, tmp_dir=os.getcwd()):
    if not path.startswith("/nix/store/"):
        raise Exception("path not valid")
    ni = NarInfo(fetch_file_from_cache(nar_info_from_path(path)))

    with tempfile.TemporaryDirectory(dir=tmp_dir) as temp_dir:
        with ccd(temp_dir):
            nar_location = os.path.join(temp_dir, os.path.basename(ni.d['URL']))
            download_file_from_cache(ni.d['URL'], nar_location, binary_cache)
            assert(os.path.isfile(nar_location))
            if ni.d['Compression'] == 'xz' and nar_location.endswith("xz"):
                nar_extract_location = ".".join(nar_location.split(".")[:-1])
                with lzma.open(nar_location) as n:
                    with open(nar_extract_location, "wb") as ne:
                        ne.write(n.read())
            elif ni.d['Compression'] == 'bzip2' and nar_location.endswith("bz2"):
                nar_extract_location = ".".join(nar_location.split(".")[:-1])
                with bz2.open(nar_location) as n:
                    with open(nar_extract_location, "wb") as ne:
                        ne.write(n.read())
            else:
                nar_extract_location = nar_location
            path_in_nar = '/'.join([''] + path.split('/')[4:])
            subprocess.run("nix cat-nar {} {} > {}".format(nar_extract_location, path_in_nar, dest_file), shell=True)
            assert(os.path.isfile(dest_file))

class NarInfoCollector:
    def __init__(self):
        self.queue = queue.Queue()
        self.work = set()
        self.work_done = set()
        self.lock = threading.Lock()
        self.collection = []

    def start(self, store_paths):
        for path in store_paths:
            self.add_work(nar_info_from_path(path))

    def get_work(self):
        return self.queue.get()

    def add_work(self, work):
        if not (work in self.work or
                work in self.work_done):
            self.work.add(work)
            self.queue.put(work)

    def turn_in(self, name, nar_info):
        n = NarInfo(nar_info)
        self.collection.append([name, n])
        nar_infos = [ nar_info_from_path(path) for path in n.d['References'].split(' ') ]

        with self.lock:
            self.work_done.add(name)
            self.work.remove(name)
            for n in nar_infos:
                if len(n):
                    self.add_work(n)
        self.queue.task_done()
