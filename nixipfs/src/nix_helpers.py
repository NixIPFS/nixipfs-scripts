import subprocess
import os

def hash_part_in_path(path):
    if path.count('/') >= 3:
        # Path in the format /nix/store/hash-name
        return path.split('/')[3][:32]
    elif path.count('/') == 0:
        # without /nix/store/
        return path[:32]
    else:
        raise Exception("malformed path")

def nar_info_from_path(path):
    h = hash_part_in_path(path)
    if len(h):
        return h + ".narinfo"
    else:
        return ""

# TODO implement in pure python
def nix_hash(path, hash_type="sha256", base="base32"):
    assert(os.path.isfile(path))
    assert(hash_type in [ "md5", "sha1", "sha256", "sha512" ])
    assert(base      in [ "base16", "base32", "base64" ])
    h_res = subprocess.run("nix hash-file --{} --type {} {}".format(base, hash_type, path), shell=True, stdout=subprocess.PIPE)
    return h_res.stdout.decode('utf-8').strip()

class NarInfo:
    def __init__(self, text = ""):
        self.d = {}
        if len(text):
            self.load(text)

    def load(self, text):
        for line in text.split('\n'):
            if line.count(':'):
                t = line.split(':', 1)
                self.d[t[0].strip()] = t[1].strip()

    def dump(self):
        res = []
        for k,v in self.d.items():
            res.append("{}: {}".format(k,v))
        # make it determinstic for hashing
        return sorted(res)

    def to_string(self):
        return '\n'.join(self.dump() + [''])
