import contextlib
import os
from progress.bar import Bar

class LJustBar(Bar):
    def __init__(self, message=None, width=16, **kwargs):
        super(Bar, self).__init__(message.ljust(max(width, len(message))), **kwargs)

@contextlib.contextmanager
def ccd(path):
    cur = os.getcwd()
    os.chdir(path)
    yield
    os.chdir(cur)
