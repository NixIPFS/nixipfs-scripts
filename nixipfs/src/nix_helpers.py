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
