class BuildInfo:
    def __init__(self, info):
        self.info = info

    @property
    def path(self):
        return self.info['buildproducts']['1']['path']

    @property
    def sha256(self):
        return self.info['buildproducts']['1']['sha256hash']

class ReleaseInfo:
    def __init__(self, info):
        self.info = info

    @property
    def id(self):
        return self.info['id']

    @property
    def name(self):
        return self.info['nixname']

    @property
    def eval_id(self):
        return self.info['jobsetevals'][0]

class EvalInfo:
    def __init__(self, info):
        self.info = info

    @property
    def git_rev(self):
        return self.info['jobsetevalinputs']['nixpkgs']['revision']
