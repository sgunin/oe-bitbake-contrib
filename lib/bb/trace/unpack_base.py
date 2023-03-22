"""Module implementing a base process for upstream source tracing

The process consists of:

- creating a temporary directory where each SRC_URI element is unpacked (if we
  unpack directly to WORKDIR, the latter may contain other files coming from
  other  SRC_URI element unpacking or from other tasks, making it much harder to
  trace  files for each SRC_URI element individually);

- collecting relevant metadata for Software Composition Analysis (file sha1,
  upstream download location (in SPDX-compliant format), path in the upstream
  repo/package, etc.);

- moving everything to WORKDIR, and iterate with the next SRC_URI element;

- saving metadata in a json file after all elements have been processed.
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

from bb.trace import TraceException

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
    if ".git" in path_scandir and path_scandir[".git"].is_dir():
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

    Conflict resolution criteria:

    - if a file (or symlink) exists both in src_dir and in dst_dir, the
      file/symlink in dst_dir will be overwritten;

    - if a subdirectory exists both in src_dir and in dst_dir, their contents
      will be merged, and in case of file/symlink conflicts, files/symlinks in
      dst_dir will be overwritten - unless src_dir is a git repo; in  such a
      case, dst_dir will be pruned and src_dir will be moved to dst_dir, for
      consistency with bb.fetch2.git.Git.unpack method's behavior (which prunes
      clone dir if already existing, before cloning)

    - if the same relative path exists both in src_dir and in dst_dir, but the
      path in src_dir is a directory and the path in dst_dir is a file/symlink,
      the latter will be overwritten;

    - if instead the path in src_dir is a file and the path in dst_dir is a
      directory, the latter will be overwritten only if it is empty, otherwise
      an exception will be raised.

    In order to reduce execution time, os.scandir is used instead of os.listdir,
    and os.rename is used to move/overwrite files, as well as to move src dir
    subdirectories that do not exist or are empty in dst_dir. To make os.rename
    work as intended, both src_dir and dst_dir must reside in the same
    filesystem.
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

def findall_files_and_links(path, exclude=[]):
    """recusively find all files and links in path, excluding dir and file names
    in exclude.

    Returns tuple of sorted lists of file and link paths. Sorting is for
    reproducibility (order of files returned by os.scandir may randomly vary)

    It uses os.scandir instead of os.walk or os.listdir because it's much faster
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
                _files, _links = findall_files_and_links(e.path, exclude)
                files += _files
                links += _links
    return sorted(files), sorted(links)


class TraceUnpackBase:
    """base class for implementing a process for upstream source tracing
    See module help for more details on the process.

    This is just a base class, that implements the process but does not collect
    any data. As such, it can be used just to test if the process correctly
    integrates with all bb fetchers.

    To be of actual use, it should be subclassed implementing _collect_data()
    and _process_data() methods.

    Method call order:
        - __init__()
        - commit()
        - move2root()
        - write_data()
        - close()
    """

    def __init__(self, root, d):
        """initialize properties and create temporary directory in root

        Temporary unpack dir is created in 'root' to be sure they are in the
        same filesystem, to allow faster moving of contents at the end.

        If some basic variables are missing from datastore (WORKDIR, PN, PV,
        BBLAYERS), it means that we are inside a fetcher test
        (self.is_fetcher_test=True); in such case, some steps (commit and
        write_data) should be skipped because they would miss required data.
        """

        self.root = root
        self.d = d
        self.td = {}
        required_vars = [ "WORKDIR", "PN", "PV", "BBLAYERS" ]
        for var in required_vars:
            if not self.d.getVar(var):
                self.is_fetcher_test = True
                break
        else:
            self.is_fetcher_test = False
        if not os.path.exists(root):
            bb.utils.mkdirhier(root)
        self.tmpdir = tempfile.mkdtemp(dir=root)

    def commit(self, u, ud, subdir=None, gitsm_revision=None):
        """collect and infer metadata by scanning self.tmpdir after unpack

        This method is generally called by bb.fetch2.Fetch.unpack() (which is a
        wrapper for fetcher-specific unpack methods).

        However in two cases (gitsm and npmsw fetchers) it needs to be called
        also by the fetcher-specific unpack method, because both gitsm and npmsw
        generate multiple src uris (modules) from one single SRC_URI element
        (main git repo or npm-shrinkwrap.json), unpack the "main" SRC_URI
        element and then unpack generated src uris. Each of such generated src
        uris corresponds to a separate upstream package (git submodule or npm
        module) which needs to be separately traced.

        Params are:

        - u -> str: src uri of the upstream repo/package that is being processed
          (eg.
          git://github.com/containernetworking/cni.git;nobranch=1;name=cni;protocol=https)

        - ud -> bb.fetch2.FetchData: src uri fetch data object. It usually
          corresponds to the fetch data of u, but when called by gitsm and npmsw
          fetchers u is the src uri of the (sub)module being processed, while ud
          is the src uri fetch data of the "main" SRC_URI element (main git repo
          or npm-shrinkwrap.json file). NOTE: ud.destdir is the destination
          directory where the "main" SRC_URI element is unpacked; it should be
          used to infer each file's path in the upstream repo/package

        - subdir -> str: subdir of ud.destdir where the (sub)module has been
          unpacked (only for gitsm and npmsw fetchers). It should be used to
          infer each file's path in the upstream repo/package

        - gitsm_revision -> str: revision of the git submodule that is being
          processed
        """
        if self.is_fetcher_test:
            return
        destdir = os.path.join(ud.destdir, subdir) if subdir else ud.destdir
        files, links = findall_files_and_links(
            destdir, exclude=['.git', '.hg', '.svn', 'node_modules'])
        self._collect_data(u, ud, files, links, destdir, gitsm_revision)

    def _collect_data(self, u, ud, files, links, destdir, gitsm_revision):
        """collect SCA metadata on the committed files. Not implemented"""
        pass

    def move2root(self):
        """move all files from temporary directory to root (=WORKDIR, generally)

        It needs to be a separate method from commit() because of the way gitsm
        and npmsw fetchers work: with such fetchers, we cannot move anything to
        root before all git|npm (sub)modules have been processed, but we need to
        commit trace data for each (sub)module individually, so commit() and
        move2root() need to be two separate methods.
        """
        move_contents(self.tmpdir, self.root)

    def _process_data(self):
        """post-process self.td - eg. to group data and optimize json output.
        Not implemented"""
        pass

    def write_data(self):
        if self.is_fetcher_test:
            return
        self._process_data()
        path = "%s/temp/%s-%s.unpack.trace.json.zst" % (
            self.d.getVar("WORKDIR"), self.d.getVar("PN"), self.d.getVar("PV"))
            # FIXME find the right way and place to store this file so that it
            # can be picked up by create-spdx even when do_unpack is not run
            # because built component is in sstate-cache
        with bb.compress.zstd.open(path, "wt", encoding="utf-8") as f:
            json.dump(self.td, f)
            f.flush()

    def close(self):
        os.rmdir(self.tmpdir)
        del self.td


