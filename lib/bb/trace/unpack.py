"""
Module implementing upstream source tracing process for do_unpack.

For the general process design, see .unpack_base module help texts.

The final output is a compressed json file, stored in WORKDIR/temp for
each recipe, with the following scheme:

{
    "<download location>": {
        "download_location": "<download location>",
        "src_uri": "<src_uri>",
        "unexpanded_src_uri": "<unexpanded src uri>",
        "checksums": {
            "md5": "<package md5 checksum>",
            "sha256": "<package sha256 checksum>"
        },
        "files": {
            "<file/relpath/in/upstream>": {
                "sha1": "<file sha1 checksum>",
                "paths_in_workdir": [
                    "<file/relpath//in/workdir>",
                    "<other/file/relpath/in/workdir>"
                ]
            }
        }
    }
}

NOTE: "download location" is used as main key/index and follows SPDX specs, eg.:
https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz
git+git://sourceware.org/git/bzip2-tests.git@f9061c030a25de5b6829e1abf373057309c734c0:

Special cases:

- npmsw and gitsm fetchers generate and unpack multiple uris (one for each
  (sub)module) from a single SRC_URI entry; each of such uris is represented by
  a separate download location in the json file, while they will all share the
  same SRC_URI entry

- npmsw fetcher collects also npm deptree data; such data are collectively
  stored within the download location entry for the npm-shrinkwrap.json file
  (which corrensponds to the npmsw:// SRC_URI entry)

- gitsm submodule dependencies are instead individually stored in the download
  location entry for each submodule (
    "submodule_of": "<main git repo's download location>")

- file:// SRC_URI entries are mapped each to a single download location,
  and file's path in upstream sources is put directly in the download
  location, in this way:
  git+git://git.yoctoproject.org/poky@91d0157d6daf4ea61d6b4e090c0b682d3f3ca60f#meta/recipes-extended/bzip2/bzip2/Makefile.am
  In such case, the "<file/relpath/in/upstream>" key will be an empty string "".
  The latter does not hold for file:// SRC_URI pointing to a directory or to an
  archive; in such cases, "<file/relpath/in/upstream>" will be relative to the
  directory or to the archive

- if no download location is found for a file:// SRC_URI entry, a warning is
  logged and an "invalid" local download location is used, trying to map it at least
  to an existing local bblayer, if any

- local absolute paths found SRC_URI entries are replaced by a placeholder
  ("<local-path>"), to allow reproducibility of json results, while the
  corresponding unexpanded SRC_URI entry is also stored to allow to trace it
  back to the corresponding recipe

For more details and handled corner cases, see help texts in
bb.tests.trace.TraceUnpackIntegrationTest and real-world data examples in
lib/bb/tests/trace-testdata.
"""

# Copyright (C) 2023 Alberto Pianon <pianon@array.eu>
#
# SPDX-License-Identifier: GPL-2.0-only
#

import os
import re
import logging

import bb.fetch2
import bb.utils
import bb.process

from ..trace import TraceException
from .unpack_base import TraceUnpackBase

logger = logging.getLogger("BitBake.Fetcher")

# function copied from https://git.openembedded.org/openembedded-core/plain/meta/lib/oe/recipeutils.py?id=ad3736d9ca14cac14a7da22c1cfdeda219665e6f
# Copyright (C) 2013-2017 Intel Corporation
def split_var_value(value, assignment=True):
    """
    Split a space-separated variable's value into a list of items,
    taking into account that some of the items might be made up of
    expressions containing spaces that should not be split.
    Parameters:
        value:
            The string value to split
        assignment:
            True to assume that the value represents an assignment
            statement, False otherwise. If True, and an assignment
            statement is passed in the first item in
            the returned list will be the part of the assignment
            statement up to and including the opening quote character,
            and the last item will be the closing quote.
    """
    inexpr = 0
    lastchar = None
    out = []
    buf = ''
    for char in value:
        if char == '{':
            if lastchar == '$':
                inexpr += 1
        elif char == '}':
            inexpr -= 1
        elif assignment and char in '"\'' and inexpr == 0:
            if buf:
                out.append(buf)
            out.append(char)
            char = ''
            buf = ''
        elif char.isspace() and inexpr == 0:
            char = ''
            if buf:
                out.append(buf)
            buf = ''
        buf += char
        lastchar = char
    if buf:
        out.append(buf)

    # Join together assignment statement and opening quote
    outlist = out
    if assignment:
        assigfound = False
        for idx, item in enumerate(out):
            if '=' in item:
                assigfound = True
            if assigfound:
                if '"' in item or "'" in item:
                    outlist = [' '.join(out[:idx+1])]
                    outlist.extend(out[idx+1:])
                    break
    return outlist

def get_unexp_src_uri(src_uri, d):
    """get unexpanded src_uri"""
    src_uris = d.getVar("SRC_URI").split() if d.getVar("SRC_URI") else []
    if src_uri not in src_uris:
        raise TraceException("%s does not exist in d.getVar('SRC_URI')" % src_uri)
    unexp_src_uris = split_var_value(
        d.getVar("SRC_URI", expand=False), assignment=False)
    for unexp_src_uri in unexp_src_uris:
        if src_uri in d.expand(unexp_src_uri).split():
            # some unexpanded src_uri with expressions may expand to multiple
            # lines/src_uris
            return unexp_src_uri
    return src_uri

find_abs_path_regex = [
    r"(?<=://)/[^;]+$",     # url path (as in file:/// or npmsw:///)
    r"(?<=://)/[^;]+(?=;)", # url path followed by param
    r"(?<==)/[^;]+$",       # path in param
    r"(?<==)/[^;]+(?=;)",   # path in param followed by another param
]
find_abs_path_regex = [ re.compile(r) for r in find_abs_path_regex ]

def get_clean_src_uri(src_uri):
    """clean expanded src_uri from possible local absolute paths"""
    for r in find_abs_path_regex:
        src_uri = r.sub("<local-path>", src_uri)
    return src_uri

def blame_recipe_file(unexp_src_uri, d):
    """return the .bb|.inc|.bbappend  file(s) which set or appended the given
    unexpanded src_uri element. Var history tracking must be enabled for this
    to work."""
    # NOTE this function is not being used for now
    haystack = []
    for el in d.varhistory.variable("SRC_URI"):
        if not el.get("parsing"):
            continue
        if el["op"] == "set":
            haystack = [ el ]
        elif "append" in el["op"] or "prepend" in el["op"]:
            haystack.append(el)
    recipe_file = [
        el["file"] for el in haystack if unexp_src_uri in el["detail"].split()
    ]
    return recipe_file[-1] if recipe_file else None

def get_dl_loc(local_dir):
    """get git upstream download location and relpath in git repo for local_dir"""
    # copied and adapted from https://git.yoctoproject.org/poky-contrib/commit/?h=jpew/spdx-downloads&id=68c80f53e8c4f5fd2548773b450716a8027d1822
    # download location cache is implemented in TraceUnpack class

    local_dir = os.path.realpath(local_dir)
    try:
        stdout, _ = bb.process.run(
            ["git", "branch", "-qr", "--format=%(refname)", "--contains", "HEAD"],
            cwd=local_dir
        )
        branches = stdout.splitlines()
        branches.sort()
        for b in branches:
            if b.startswith("refs/remotes") and not b.startswith("refs/remotes/m/"):
                # refs/remotes/m/ -> repo manifest remote, it's not a real
                # remote (see https://stackoverflow.com/a/63483426)
                remote = b.split("/")[2]
                break
        else:
            return None, None

        stdout, _ = bb.process.run(
            ["git", "remote", "get-url", remote], cwd=local_dir
        )
        dl_loc = "git+" + stdout.strip()

        stdout, _ = bb.process.run(["git", "rev-parse", "HEAD"], cwd=local_dir)
        dl_loc = dl_loc + "@" + stdout.strip()

        stdout, _ = bb.process.run(
            ["git", "rev-parse", "--show-prefix"], cwd=local_dir)
        relpath = os.path.join(stdout.strip().rstrip("/"))

        return dl_loc, relpath

    except bb.process.ExecutionError:
        return None, None

def get_untracked_new_and_modified_files(git_dir):
    """get list of untracked or uncommitted new or modified files in git_dir"""
    try:
        bb.process.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=git_dir)
    except bb.process.ExecutionError:
        raise TraceException("%s is not a git repo" % git_dir)
    stdout, _ = bb.process.run(["git", "status", "--porcelain"], cwd=git_dir)
    return [ line[3:] for line in stdout.rstrip().split("\n") ]

def get_path_in_upstream(f, u, ud, destdir):
    """get relative path in upstream package, relative to download location"""
    relpath = os.path.relpath(f, destdir)
    if ud.type == "file":
        is_unpacked_archive = getattr(ud, "is_unpacked_archive", False)
        if os.path.isdir(ud.localpath) or is_unpacked_archive:
            return os.path.relpath(relpath, ud.path)
        else:
            # it's a file, its path is already in download location, like
            # in git+https://git.example.com/foo#example/foo.c so there is
            # no relative path to download location
            return ""
    elif ud.type == "npmsw" and ud.url == u:
        # npm shrinkwrap file
        return ""
    else:
        return relpath

class TraceUnpack(TraceUnpackBase):
    """implement a process for upstream source tracing in do_unpack

    Subclass of TraceUnpackBase, implementing _collect_data() and
    _process_data() methods

    See bb.trace.unpack_base module help for more details on the process.

    See bb.tests.trace.TraceUnpackIntegrationTest and data examples in
    lib/bb/tests/trace-testdata for details on the output json data format.

    Method call order:
        - __init__()
        - commit()
        - move2root()
        - write_data()
        - close()
    """

    def __init__(self, root, d):
        """create temporary directory in root, and initialize cache"""
        super(TraceUnpack, self).__init__(root, d)

        self.local_path_cache = {}
        self.src_uri_cache = {}
        self.shrinkwrap_cache = {}
        self.upstr_data_cache = {}
        self.package_checksums_cache = {}
        self.git_dir_cache = {}
        if not self.is_fetcher_test:
            self.layers = {
                os.path.basename(l): os.path.realpath(l)
                for l in d.getVar('BBLAYERS').split()
            }
        else:
            self.layers = {}

    def _collect_data(self, u, ud, files, links, destdir, gitsm_revision):
        """collect data for the "committed" src uri entry (u)

        data are saved using path_in_workdir as index; for each path_in_workdir,
        sha1 checksum and upstream data are collected (from cache, if available,
        because self._get_upstr_data_wrapper() uses a cache)

        sha1 and upstream data are appended to a list for each path_in_workdir,
        because it may happen that a file unpacked from a src uri gets
        overwritten by a subsequent src uri, from which a file with the same
        name/path is unpacked; the overwrite would be captured in the list.

        At the end, all data will be processed and grouped by download location
        by self._process_data(), that will keep only the last item of
        sha1+upstream data list for each path_in_workdir
        """
        upstr_data = self._get_upstr_data_wrapper(u, ud, destdir, gitsm_revision)
        for f in files:
            sha1 = bb.utils.sha1_file(f)
            path_in_workdir = os.path.relpath(f, self.tmpdir)
            path_in_upstream = get_path_in_upstream(f, u, ud, destdir)
            data = self.td.setdefault(path_in_workdir, [])
            data.append({
                "sha1": sha1,
                "path_in_upstream": path_in_upstream,
                "upstream": upstr_data,
            })
        for l in links:
            link_target = os.readlink(l)
            path_in_workdir = os.path.relpath(l, self.tmpdir)
            path_in_upstream = get_path_in_upstream(l, u, ud, destdir)
            data = self.td.setdefault(path_in_workdir, [])
            data.append({
                "symlink_to": link_target,
                "path_in_upstream": path_in_upstream,
                "upstream": upstr_data,
            })

    def _process_data(self):
        """group data by download location"""
        # it reduces json file size and allows faster processing by create-spdx
        pd = self.upstr_data_cache
        for workdir_path, data in self.td.items():
            data = data[-1] # pick last overwrite of the file, if any
            dl_loc = data["upstream"]["download_location"]
            files = pd[dl_loc].setdefault("files", {})
            path = data["path_in_upstream"]
            if path in files:
                files[path]["paths_in_workdir"].append(workdir_path)
                # the same source file may be found in different locations in
                # workdir, eg. with npmsw fetcher, where the same npm module
                # may unpacked multiple times in different paths
            else:
                path_data = files[path] = {}
                if data.get("sha1"):
                    path_data.update({ "sha1": data["sha1"] })
                elif data.get("symlink_to"):
                    path_data.update({ "symlink_to": data["symlink_to"] })
                path_data.update({ "paths_in_workdir": [workdir_path] } )
        self.td = pd

    def close(self):
        super(TraceUnpack, self).close()
        del self.local_path_cache
        del self.src_uri_cache
        del self.shrinkwrap_cache
        del self.upstr_data_cache
        del self.package_checksums_cache
        del self.layers

    def _get_layer(self, local_path):
        """get bb layer for local_path (must be a realpath)"""
        for layer, layer_path in self.layers.items():
            if local_path.startswith(layer_path):
                return layer
        return None

    def _is_in_current_branch(self, file_relpath, git_dir):
        """wrapper for get_untracked_new_and_modified_files(), using cache
        for already processed git dirs"""
        if git_dir not in self.git_dir_cache:
            self.git_dir_cache[git_dir] = get_untracked_new_and_modified_files(git_dir)
        untracked_new_and_modified_files = self.git_dir_cache[git_dir]
        return file_relpath not in untracked_new_and_modified_files

    def _get_dl_loc_and_layer(self, local_path):
        """get download location, upstream relative path and layer for local_path

        Wrapper for get_dl_loc() and TraceUnpack._get_layer(), using cache for
        already processed local paths, and handling also file local paths and
        not only dirs.
        """
        local_path = os.path.realpath(local_path)
        if local_path not in self.local_path_cache:
            if os.path.isdir(local_path):
                dl_loc, relpath = get_dl_loc(local_path)
                layer = self._get_layer(local_path)
                self.local_path_cache[local_path] = (dl_loc, relpath, layer)
            else:
                local_dir, basename = os.path.split(local_path)
                dl_loc, dir_relpath, layer = self._get_dl_loc_and_layer(local_dir)
                file_relpath = os.path.join(dir_relpath, basename) if dir_relpath else None
                if file_relpath:
                    if local_path.endswith(file_relpath):
                        git_dir = local_path[:-(len(file_relpath))].rstrip("/")
                    else:
                        raise TraceException(
                            "relative path %s is not in %s" %
                            (file_relpath, local_path)
                        )
                    if not self._is_in_current_branch(file_relpath, git_dir):
                        dl_loc = file_relpath = None # is untracked|new|modified
                self.local_path_cache[local_path] = (dl_loc, file_relpath, layer)
        return self.local_path_cache[local_path]

    def _get_unexp_and_clean_src_uri(self, src_uri):
        """get unexpanded and clean (i.e. w/o local paths) expanded src uri

        Wrapper for get_unexp_src_uri() and clean_src_uri(), using cache for
        already processed src uris
        """
        if src_uri not in self.src_uri_cache:
            try:
                unexp_src_uri = get_unexp_src_uri(src_uri, self.d)
            except TraceException:
                unexp_src_uri = src_uri
            clean_src_uri = get_clean_src_uri(src_uri)
            self.src_uri_cache[src_uri] = (unexp_src_uri, clean_src_uri)
        return self.src_uri_cache[src_uri]

    def _get_package_checksums(self, ud):
        """get package checksums for ud.url

        Checksums, if available, apparently refer only to the first SRC_URI
        entry that supports checksums, so if there are multiple SRC_URI entries
        supporting checksum, we pick the checksums only for the first one.
        For this reason self.package_checksums_cache dict will needs to contain
        only one element
        """
        if not self.package_checksums_cache:
            checksums = {}
            if ud.method.supports_checksum(ud):
                for checksum_id in bb.fetch2.CHECKSUM_LIST:
                    expected_checksum = getattr(ud, "%s_expected" % checksum_id)
                    if expected_checksum is None:
                        continue
                    checksums.update({checksum_id: expected_checksum})
            self.package_checksums_cache[ud.url] = checksums
        return self.package_checksums_cache.get(ud.url, {})

    def _get_upstr_data(self, src_uri, ud=None, local_path=None, gitsm_revision=None):
        """get upstream data for src_uri

        ud is required for non-file src_uris, while local_path is required for
        file src_uris; gitsm_revision is required for git submodule src_uris
        """
        if local_path:
            # file src_uri
            dl_loc, relpath, layer = self._get_dl_loc_and_layer(local_path)
            if dl_loc:
                dl_loc += "#" + relpath
            else:
                # we didn't find any download location so we set a fake (but
                # unique) one because we need to use it as key in the final json
                # output
                if layer:
                    relpath_in_layer = os.path.relpath(
                        os.path.realpath(local_path), self.layers[layer])
                    dl_loc = "file://<local-path>/" + layer + "/" + relpath_in_layer
                else:
                    dl_loc = "file://" + local_path
                    relpath = ""
                logger.warning(
                    "Can't find upstream source for %s, using %s as download location" %
                    (local_path, dl_loc)
                )
            get_checksums = False
        else:
            # copied and adapted from https://git.yoctoproject.org/poky/plain/meta/classes/create-spdx-2.2.bbclass
            if ud and src_uri == ud.url:
                this_ud = ud
            else:
                this_ud = bb.fetch2.FetchData(src_uri, self.d)
            if this_ud.type == "crate":
                # crate fetcher converts crate:// urls to https://
                this_ud = bb.fetch2.FetchData(this_ud.url, self.d)
            dl_loc = this_ud.type
            if dl_loc == "gitsm":
                dl_loc = "git"
            proto = getattr(this_ud, "proto", None)
            if proto is not None:
                dl_loc = dl_loc + "+" + proto
            dl_loc = dl_loc + "://" + this_ud.host + this_ud.path
            if gitsm_revision:
                dl_loc = dl_loc + "@" + gitsm_revision
            elif this_ud.method.supports_srcrev():
                dl_loc = dl_loc + "@" + this_ud.revisions[this_ud.names[0]]
            layer = None
            get_checksums = True
        if dl_loc not in self.upstr_data_cache:
            self.upstr_data_cache[dl_loc] = {
                "download_location": dl_loc,
            }
            uri = src_uri if not gitsm_revision else ud.url
            unexp_src_uri, clean_src_uri = self._get_unexp_and_clean_src_uri(uri)
            self.upstr_data_cache[dl_loc].update({
                "src_uri": clean_src_uri
            })
            if unexp_src_uri != clean_src_uri:
                self.upstr_data_cache[dl_loc].update({
                    "unexpanded_src_uri": unexp_src_uri
                })
            if get_checksums:
                checksums = self._get_package_checksums(this_ud)
                if checksums:
                    self.upstr_data_cache[dl_loc].update({
                        "checksums": checksums
                    })
            if layer:
                self.upstr_data_cache[dl_loc].update({
                    "layer": layer
                })
        return self.upstr_data_cache[dl_loc]

    def _get_npm_shrinkwrap_deptree(self, ud):
        """Process dep data from ud.deps (npm dependency data collected by npmsw
        fetcher) and return a deptree in the following format:

        "foo": {
            "version": "0.0.1",
            "download_location": "https://npm.example.com/foo/0.0.1",
            "deps": {
                "dummy": {
                    "version": "0.1.0",
                    "download_location": "https://npm.example.com/dummy/0.1.0",
                }
            }
        }
        """

        def clean(deptree_node):
            for module_name, data in deptree_node.items():
                if data["deps"] != {}:
                    deptree_node = data["deps"]
                    clean(deptree_node)
                else:
                    data.pop("deps")

        indexed_deptree_data = {tuple(dep["deptree"]): dep for dep in ud.deps}
            # ud.deps elements are npm module paths within deptree, in list
            # format, such as [ 'foo', ], [ 'foo', 'dummy' ] etc. Converting
            # them to tuples to use them as index
        deptree = {}
        for dep_path in sorted(indexed_deptree_data):
            for i in range(1, len(dep_path)+1):
                deptree_node = deptree
                _dep_path = dep_path[:i]
                data = indexed_deptree_data[_dep_path]
                for module_name in _dep_path:
                    module = deptree_node.get(module_name)
                    if not module:
                        upstr_data = self._get_upstr_data(data["url"])
                        module = {
                            "version": data["version"],
                            "download_location": upstr_data["download_location"],
                        }
                        if upstr_data.get("checksums"):
                            module.update({"checksums": upstr_data["checksums"]})
                        module.update({"deps": {}})
                    deptree_node[module_name] = module
                    deptree_node = module["deps"]
        clean(deptree)
        return deptree

    def _get_upstr_data_wrapper(self, u, ud, destdir, gitsm_revision=None):
        """wrapper for self._get_upstr_data(), handling npmsw and gitsm fetchers
        (that require some recursion)"""
        if ud.type == "npmsw":
            if ud.url == u:
                # npm-shrinkwrap.json file
                upstr_data = self._get_upstr_data(
                    ud.url, local_path=ud.shrinkwrap_file)
                upstr_data.update({
                    "deptree": self._get_npm_shrinkwrap_deptree(ud)
                })
                self.shrinkwrap_cache[ud.url] = upstr_data["download_location"]
            else:
                # ud.url is the "main" src_uri of the shrinkwrap file,
                # while u is the fetcher-generated src_uri for the module
                module_ud = bb.fetch2.FetchData(u, self.d)
                upstr_data = self._get_upstr_data_wrapper(u, module_ud, destdir)
                    # recursively call this method
                upstr_data.update({
                    "described_by": self.shrinkwrap_cache[ud.url]
                })
        elif ud.type == "gitsm":
            upstr_data = self._get_upstr_data(
                u, ud=ud, gitsm_revision=gitsm_revision)
            if ud.url != u:
                # git submodule
                parent_upstr_data = self._get_upstr_data(ud.url, ud)
                upstr_data.update({
                    "submodule_of": parent_upstr_data["download_location"]
                })
                # known limitation: this logic cannot correctly handle
                # nested git submodules, because it assumes only one level of
                # submodule dependencies.
                # TODO Some more logic would need to be added to gitsm fetcher,
                # to add support for nested git submodule dependency mapping
        elif ud.type == "file":
            upstr_data = self._get_upstr_data(u, local_path=ud.localpath)
        else:
            upstr_data = self._get_upstr_data(u, ud)
        return upstr_data


