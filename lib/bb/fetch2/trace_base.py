"""Module implementing a base process for upstream source tracing
for bb.fetch2.Fetch.unpack()

The process consists of:

- creating a temporary directory where each SRC_URI element is unpacked

- collecting relevant metadata (provenance) for each source file and for every
  upstream source component, that can be used later on for Software Composition
  Analysis, SBoM generation, etc.;

- moving everything from the temporary directory to root, and iterate with the
  next SRC_URI element;

- saving metadata in a json file after all elements have been processed.

It assumes that:

- fetchers store unpack destination dir in urldata.destdir;
- gitsm and npmsw fetchers store module metadata in urldata.module_data, as a
  list of dict elements in the following format:
    [
        {
            "url": "<module url>",
            "destdir": "<module destination path>",
            "parent_destdir": "<parent module destination path>"
            "revision": "<git submodule revision (only for gitsm, else None)>"
        }, ...
    ]
- urldata.is_unpacked_archive (boolean) is set to True or False for "file"
  SRC_URI entries.
"""

# Copyright (C) 2023 Alberto Pianon <pianon@array.eu>
#
# SPDX-License-Identifier: GPL-2.0-only
#

import os
import json
import tempfile

import bb.utils
import bb.compress.zstd

class TraceException(Exception):
    pass

def scandir(path):
    with os.scandir(path) as scan:
        return { e.name: e for e in scan }

def is_real_dir(e):
    return e.is_dir() and not e.is_symlink()

def is_real_and_nonempty_dir(e):
    return is_real_dir(e) and scandir(e.path)

def is_file_or_symlink(e):
    return e.is_file() or e.is_symlink()

def is_git_dir(e):
    path_scandir = scandir(e.path)
    if ".git" in path_scandir:
        try:
            bb.process.run(
                ["git", "rev-parse", "--is-inside-work-tree"], cwd=e.path)
            return True
        except bb.process.ExecutionError:
            return False
    return False

def check_is_real_dir(path, name):
    if not os.path.exists(path) or os.path.islink(path) or os.path.isfile(path):
        raise TraceException(
            "%s path %s is not a directory" % (name, path))

def move_contents(src_dir, dst_dir):
    """Move and merge contents from src_dir to dst_dir

    Conflict resolution criteria are explained in bb.tests.trace_base

    It's optimized for fast execution time by using os.scandir and os.rename, so
    it requires that both src_dir and dst_dir reside in the same filesystem.
    """

    check_is_real_dir(src_dir, "Source")
    check_is_real_dir(dst_dir, "Destination")

    if os.lstat(src_dir).st_dev != os.lstat(dst_dir).st_dev:
        raise TraceException(
            "Source %s and destination %s must be in the same filesystem" %
            (src_dir, dst_dir)
        )

    src_scandir = scandir(src_dir)
    dst_scandir = scandir(dst_dir)

    for src_name, src in src_scandir.items():
        dst = dst_scandir.get(src_name)
        if dst:
            # handle conflicts
            if is_real_dir(src) and is_real_and_nonempty_dir(dst):
                if is_git_dir(src):
                    bb.utils.prunedir(dst.path)
                else:
                    move_contents(src.path, dst.path)
                    os.rmdir(src.path)
                    continue
            elif is_real_dir(src) and is_file_or_symlink(dst):
                os.remove(dst.path)
            elif is_file_or_symlink(src) and is_real_dir(dst):
                try:
                    os.rmdir(dst.path)
                except OSError as e:
                    if e.errno == 39:
                        raise TraceException(
                            "Error while moving %s contents to %s, cannot move"
                            " %s to %s: source is a file or a symlink, while"
                            " destination is a non-empty directory."
                            % (src_dir, dst_dir, src.path, dst.path)
                        )
                    else:
                        raise e
        dst_path = dst.path if dst else os.path.join(dst_dir, src_name)
        os.rename(src.path, dst_path)

def findall_files_and_links(path, exclude=[], skip_git_submodules=False):
    """recusively find all files and links in path, excluding dir and file names
    in exclude, and excluding git dirs if skip_git_submodules is set to True.

    Returns tuple of sorted lists of file and link paths (sorting is for
    reproducibility in tests)
    """
    files = []
    links = []
    with os.scandir(path) as scan:
        for e in scan:
            if e.name in exclude:
                continue
            if e.is_symlink():
                links.append(e.path)
            elif e.is_file():
                files.append(e.path)
            elif e.is_dir():
                if skip_git_submodules and is_git_dir(e):
                    continue
                _files, _links = findall_files_and_links(
                        e.path, exclude, skip_git_submodules)
                files += _files
                links += _links
    return sorted(files), sorted(links)

class TraceUnpackBase:
    """base class for implementing a process for upstream source tracing
    See this module's help for more details on the process.

    This base class implements the process but does not collect any data. It is
    intended to be subclassed in a separate 'trace' module, implementing
    _collect_data() and _process_data() methods.

    Method call order:
        - __init__(): initialize tmpdir and td (trace data)
        - for each SRC_URI entry unpack:
          - commit(): go through all files in tmpdir (and in each module subdir
            in case of gitsm and npmsw fecthers) and commit collected metadata
            to td
          - move2root(): moves all files from tmpdir to root
        - write_data()
        - close(): delete tmpdir and cache
    """

    def __init__(self, root, d):
        """initialize properties and create temporary directory in root

        Temporary unpack dir is created in 'root' to ensure they are in the
        same filesystem, so files can be quickly moved to 'root' after tracing
        """

        self.root = root
        self.d = d
        self.td = {}
        if not os.path.exists(root):
            bb.utils.mkdirhier(root)
        self.tmpdir = tempfile.mkdtemp(dir=root)

    def commit(self, u, ud):
        """go through all files in tmpdir and commit collected metadata to td.
        dive into module subdirs in case of gitsm and npmsw fecthers

        Params are:
        - u -> str: src uri of the upstream repo/package that is being processed
        - ud -> bb.fetch2.FetchData: src uri fetch data object; ud.url and u do not correspond when git/npm modules are being processed, so we need both
        """

        exclude=['.git', '.hg', '.svn']

        # exclude node_modules subdirs (will be separately parsed)
        if ud.type in ['npm', 'npmsw']:
            exclude.append('node_modules')
        # exclude git submodules (will be separately parsed)
        skip_git_submodules = (ud.type == 'gitsm')

        files, links = findall_files_and_links(
            ud.destdir, exclude, skip_git_submodules)
        self._collect_data(u, ud, files, links, ud.destdir)

        if ud.type in ['gitsm', 'npmsw'] and ud.module_data:
            self._process_module_data(ud)
            for md in ud.module_data:
                files, links = findall_files_and_links(
                   md["destdir"], exclude, skip_git_submodules)
                self._collect_data(
                    md["url"], ud, files, links, md["destdir"], md)

    def _process_module_data(self, ud):
        """add parent module data to each module data item, to map dependencies
        """
        revision = ud.revisions[ud.names[0]] if ud.type == 'gitsm' else None
        indexed_md = { md["destdir"]: md for md in ud.module_data }
        # add main git repo (gitsm) or npm-shrinkwrap.json (npmsw)
        indexed_md.update({
                ud.destdir.rstrip("/"): {"url": ud.url, "revision": revision}
        })
        for md in ud.module_data:
            md["parent_md"] = indexed_md[md["parent_destdir"]]

    def move2root(self):
        """move all files from temporary directory to root"""
        move_contents(self.tmpdir, self.root)

    def write_data(self):
        self._process_data()
        if not self.d.getVar("PN"):
            return
        if not os.path.exists("%s/temp" % self.root):
            bb.utils.mkdirhier("%s/temp" % self.root)
        path = "%s/temp/%s-%s.unpack.trace.json.zst" % (
            self.root, self.d.getVar("PN"), self.d.getVar("PV"))
        with bb.compress.zstd.open(path, "wt", encoding="utf-8") as f:
            json.dump(self.td, f)
            f.flush()

    def close(self):
        os.rmdir(self.tmpdir)
        del self.td

    def _collect_data(self, u, ud, files, links, destdir, md=None):
        """
        collect provenance metadata on the committed files. Not implemented
        """
        pass

    def _process_data(self):
        """post-process self.td. Not implemented"""
        pass