import urllib.request
import json
import os

from nixipfs.download_helpers import fetch_json, fetch_store_path
from nixipfs.hydra_helpers import *
from nixipfs.defaults import *

class KarkinosURLopener(urllib.request.FancyURLopener):
    version = "Karkinos/11.11"

class Karkinos:
    def __init__(self, hydra_url, eval_id, binary_cache = DEFAULT_BINARY_CACHE_URL):
        urllib._urlopener = KarkinosURLopener()
        self.hydra_url = hydra_url
        self.binary_cache = binary_cache
        self.eval_id   = eval_id

    @property
    def eval_url(self):
        return "{}/eval/{}".format(self.hydra_url, self.eval_id)

    @property
    def store_path_url(self):
        return "{}/store-paths".format(self.eval_url)

    def build_info_url(self, jobname):
        return "{}/job/{}".format(self.eval_url, jobname)

    def fetch_eval_info(self):
        return fetch_json(self.eval_url)

    def fetch_store_paths(self):
        return fetch_json(self.store_path_url)

    def fetch_build_info(self, jobname):
        return fetch_json(self.build_info_url(jobname))

    def download_file(self, jobname, dest_dir, dest_name='', tmp_dir=os.getcwd()):
        build_info = BuildInfo(self.fetch_build_info(jobname))
        store_path = "/".join(build_info.path.split("/")[:4])

        if len(dest_name) == 0:
            dest_name = os.path.basename(build_info.path)
        dest_file = os.path.join(dest_dir, dest_name)
        if not os.path.isfile(dest_file):
            fetch_store_path(build_info.path, dest_file, self.binary_cache, tmp_dir)
