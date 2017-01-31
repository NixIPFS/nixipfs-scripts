#!/usr/bin/env python3
import os

def find_garbage(cache, releases, keep=[]):
    links = set()
    for release in releases:
        linked_cache_path = os.path.join(release, 'binary_cache')
        links.update(set(
            [ e for e in os.listdir(linked_cache_path) if '.narinfo' in e ]))
        links.update(set(
            [ os.path.join('nar', e) for e in os.listdir(os.path.join(linked_cache_path, 'nar')) if '.nar' in e ]))

    files = set()
    files.update(set(
        [ e for e in os.listdir(cache) if '.narinfo' in e ]))
    files.update(set(
        [ os.path.join('nar', e) for e in os.listdir(os.path.join(cache, 'nar')) if '.nar' in e ]))
    return files.difference(links)

def garbage_collect(cache, releases, keep=[]):
    garbage = find_garbage(cache, releases, keep)
    for g in garbage:
        if os.path.isfile(os.path.join(cache, g)):
            print("Deleting {}".format(g))
            os.unlink(os.path.join(cache, g))
