import os
import hashlib
import time
import json

import bb.process
import bb.utils
import bb.compress.zstd

def is_git_dir(e):
    if ".git" in os.listdir(e.path):
        try:
            bb.process.run(
                ["git", "rev-parse", "--is-inside-work-tree"], cwd=e.path)
            return True
        except bb.process.ExecutionError:
            return False
    return False

def scandir(path, exclude=[], skip_git_submodules=False):

    def _scandir(path, tree, excluded_list, exclude, skip_git_submodules):
        with os.scandir(path) as scan:
            scandir = [ e for e in scan ]
        for e in scandir:
            if e.name in exclude:
                excluded_list.append(e.path)
                continue
            if e.is_dir() and not e.is_symlink():
                if skip_git_submodules and is_git_dir(e):
                    excluded_list.append(e.path)
                    continue
                _scandir(e.path, tree, excluded_list, exclude, skip_git_submodules)
            else:
                tree[e.path] = e

    tree = {}
    excluded_list = []
    _scandir(path, tree, excluded_list, exclude, skip_git_submodules)
    paths = list(tree.keys())
    sorted_tree = {path: tree[path] for path in sorted(paths)}
    return sorted_tree, sorted(excluded_list)


def calculate_sha1(path):
    sha1 = hashlib.sha1()
    with open(path, 'rb') as file:
        while chunk := file.read(8192):
            sha1.update(chunk)
    return sha1.hexdigest()

def get_stats(e):
    s = e.stat()
    return (s.st_mode, s.st_mtime, s.st_ctime, s.st_size)

class FileIndexException(Exception):
    pass

class FileIndexEntry(object):
    def __init__(self, stats, link, sha1, last_update):
        self.stats = stats
        self.link = link
        self.sha1 = sha1
        self.last_update = last_update

class FileIndex(object):

    UNCHANGED = 0
    ADDED = 1
    MODIFIED = 2
    REMOVED = 3

    def __init__(self, root, exclude=[], skip_git_submodules=False):
        self.entries = {}
        self.root = root
        self.exclude = exclude
        self.skip_git_submodules = skip_git_submodules
        self.update_index(root)

    def _add_or_update_entry(self, e, link, timestamp, stats=None, sha1=None):
        self.entries[e.path] = FileIndexEntry(
            stats = (stats or get_stats(e)) if not link else None,
            link = link,
            sha1 = (sha1 or calculate_sha1(e.path)) if not link else None,
            last_update = int(timestamp)
        )

    def add_or_update_entry(self, e, timestamp=None):
        if not timestamp:
            timestamp = time.time()
        link = os.readlink(e.path) if e.is_symlink() else None
        if e.path in self.entries:
            entry = self.entries[e.path]
            if link:
                if link != entry.link:
                    self._add_or_update_entry(e, link, timestamp),
                    return FileIndex.MODIFIED
                else:
                    return FileIndex.UNCHANGED
            mode, mtime, ctime, size = stats = get_stats(e)
            if entry.stats != stats:
                self._add_or_update_entry(e, link, timestamp, stats)
                return FileIndex.MODIFIED
            elif (entry.last_update <= int(mtime)
                or entry.last_update <= int(ctime)
            ):
                sha1 = calculate_sha1(e.path)
                if sha1 != entry.sha1:
                    self._add_or_update_entry(e, link, timestamp, stats, sha1)
                    return FileIndex.MODIFIED
            return FileIndex.UNCHANGED
        else:
            self._add_or_update_entry(e, link, timestamp)
            return FileIndex.ADDED

    def remove_entry(self, path):
        if path in self.entries:
            del self.entries[path]
            return FileIndex.REMOVED
        return FileIndex.UNCHANGED

    def update_index(self, path, skip_node_submodules=False, skip_git_submodules=False):
        if not path.startswith(self.root):
            raise FileIndexException(
                "Cannot update index for path %s, because it is not inside"
                " index root dir %s" % (path, self.root)
            )
        timestamp = time.time()
        extra_exclude = ["node_modules"] if skip_node_submodules else []
        exclude = self.exclude + extra_exclude
        tree, excluded_list = scandir(path, exclude, skip_git_submodules)
        files = {}
        links = {}
        for p, e in tree.items():
            res = self.index.add_or_update_entry(e, timestamp)
            if res in [FileIndex.ADDED, FileIndex.MODIFIED]:
                entry = self.index.entries[e.path]
                relpath = os.path.relpath(e.path, self.root)
                if entry.sha1:
                    files[relpath] = entry.sha1
                elif entry.link:
                    links[relpath] = entry.link
        removed = []
        for p in self.index.entries:
            abspath = os.path.join(self.root, p)
            if not abspath.startswith(path):
                continue
            for excluded_path in excluded_list:
                if abspath.startswith(excluded_path):
                    break
            else:
                if path not in tree:
                    removed.append(p)
        for p in removed:
            res = self.index.remove_entry(p)
        return files, links, removed


class UrlTraceData(object):
    def __init__(self, ud, unpackdir, checkout_dir, is_module):
        self.ud = ud
        self.unpackdir = unpackdir
        self.is_module = is_module
        self.module_data = []
        self.unpackdir = None
        self.is_extracted_archive = False

class ModuleData(object):
    def __init__(self, url, name, path, parent_path, revision=None):
        self.url = url
        self.name = name
        self.path = path
        self.parent_path = parent_path
        self.revision = revision

class UnpackTracer(object):

    def __init__(self):
        self.url_td = {}
        self.file_index = None
        self.unpack_trace = []
        self.d = None
        self.root_unpackdir = None
        self.unpackdir = None
        self.url = None
        self.is_module = False

    def _start(self, unpackdir, ud_dict, d, is_module=False):
        if not self.file_index:
            self.root_unpackdir = unpackdir
            self.file_index = FileIndex(self.root_unpackdir)
            self.d = d
        self.unpack_dir = unpackdir
        self.is_module = is_module
        for url, ud in ud_dict.items():
            url_td.setdefault(
                (url, unpackdir),
                UrlTraceData(ud, unpackdir, is_module)
            )

    def start(self, unpackdir, ud_dict, d):
        self._start(self, unpackdir, ud_dict, d)

    def start_module(self, module_type, unpackdir, ud_dict, parent_ud, d):
        if module_type == "git":
            self._start(self, unpackdir, ud_dict, d, is_module=True)

    def _get_url_tracedata(self):
        return self.url_td[(self.url, self.unpackdir)]

    def start_url(self, url):
        self.url = url

    def finish_url(self, url):
        if self.is_module:
            return
        utd = self._get_url_tracedata()





    def _set_url_tracedata(self, name, value):
        utd = self.url_td[(self.url, self.unpackdir)]
        setattr(utd, name, value)

    def unpack(self, unpack_type, unpackdir, ud):
        self._set_url_tracedata("is_unpacked_archive", unpack_type == "archive-extract")
        self._set_url_tracedata("unpackdir", unpackdir)
        if unpack_type == "git":
            if not hasattr(ud, "trace_checkout_dir"):
                ud.trace_checkout_dir = ud.destdir

    def module(self, module_type, url, name, path, revision=None):
        utd = self._get_url_tracedata()
        if module_type == "git":
            parent_path = utd.ud.checkout_dir.rstrip("/")
            path = os.path.join(parent_path, path).rstrip("/")
        elif module_type == "npm":
            path = os.path.join(utd.unpackdir, path)
            parent_path = re.sub("/node_modules/"+name+"$", "", path)
        utd.module_data.append(
            ModuleData(url, name, path, parent_path, revision))
        # FIXME module_type == "npm"

    def start_git_module(self, ud, parent_ud, path, d):
        ud.checkout_dir = os.path.join(parent_ud.checkout_dir, modpath)
        self._start(ud.checkout_dir,)











    def finish_url(self, url):
        pass

    def complete(self):
        pass
        # NOTE: delete object!