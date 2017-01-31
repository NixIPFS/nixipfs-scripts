import contextlib
import os

@contextlib.contextmanager
def ccd(path):
    cur = os.getcwd()
    os.chdir(path)
    yield
    os.chdir(cur)
