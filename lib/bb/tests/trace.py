
# Copyright (C) 2023 Alberto Pianon <pianon@array.eu>
#
# SPDX-License-Identifier: GPL-2.0-only
#

import os
import re
import json
import shutil
import unittest
import tempfile
from pathlib import Path
import subprocess

import bb

from bb.tests.trace_base import create_file

def skipIfNoNetwork():
    if os.environ.get("BB_SKIP_NETTESTS") == "yes":
        return unittest.skip("network test")
    return lambda f: f

class SplitVarValueTest(unittest.TestCase):

    def test_split_var_value_with_items_without_spaces(self):
        items_without_spaces = [
            "git://github.com/systemd/systemd-stable.git;protocol=https;branch=${SRCBRANCH}",
            "${SRC_URI_MUSL}",
            "file://0001-Adjust-for-musl-headers.patch"
        ]
        var_value = " ".join(items_without_spaces)
        self.assertEqual(
            bb.trace.unpack.split_var_value(var_value, False), items_without_spaces)

    def test_split_var_value_with_items_with_spaces(self):
        items_with_spaces = [
            "https://github.com/shadow-maint/shadow/releases/download/v${PV}/${BP}.tar.gz",
            "${@bb.utils.contains('PACKAGECONFIG', 'pam', '${PAM_SRC_URI}', '', d)}",
            "file://shadow-relaxed-usernames.patch",
        ]
        var_value = " ".join(items_with_spaces)
        self.assertEqual(
            bb.trace.unpack.split_var_value(var_value, False), items_with_spaces)


class GetUnexpSrcUriTest(unittest.TestCase):

    def test_get_unexp_src_uri(self):
        d = bb.data.init()
        d.setVar("SRCBRANCH", "main")
        d.setVar("SRC_URI", """
            git://github.com/systemd/systemd-stable.git;protocol=https;branch=${SRCBRANCH}
            file://0001-Adjust-for-musl-headers.patch
        """)
        src_uri = "git://github.com/systemd/systemd-stable.git;protocol=https;branch=main"
        unexp_src_uri = "git://github.com/systemd/systemd-stable.git;protocol=https;branch=${SRCBRANCH}"
        self.assertEqual(
            bb.trace.unpack.get_unexp_src_uri(src_uri, d), unexp_src_uri)

    def test_get_unexp_src_uri_that_expands_to_multiple_items(self):
        d = bb.data.init()
        d.setVar("SRC_URI_MUSL", """
            file://0003-missing_type.h-add-comparison_fn_t.patch
            file://0004-add-fallback-parse_printf_format-implementation.patch
            file://0005-src-basic-missing.h-check-for-missing-strndupa.patch
        """)
        d.setVar("SRC_URI", """
            git://github.com/systemd/systemd-stable.git;protocol=https;branch=main
            ${SRC_URI_MUSL}
            file://0001-Adjust-for-musl-headers.patch
        """)
        src_uris = [
            "file://0003-missing_type.h-add-comparison_fn_t.patch",
            "file://0004-add-fallback-parse_printf_format-implementation.patch",
            "file://0005-src-basic-missing.h-check-for-missing-strndupa.patch",
        ]
        unexp_src_uri = "${SRC_URI_MUSL}"
        for src_uri in src_uris:
            self.assertEqual(
                bb.trace.unpack.get_unexp_src_uri(src_uri, d), unexp_src_uri)


class GetCleanSrcUriTest(unittest.TestCase):

    def test_get_clean_src_uri_from_src_uri_with_abs_path_in_param(self):
        src_uris = {
            "git://git.example.com/foo/foo-plugin1.git;destsuffix=/home/user/poky/build/tmp/work/core2-64-poky-linux/foo/0.0.1/foo-0.0.1/plugins/1;name=plugin1;protocol=https" :
                "git://git.example.com/foo/foo-plugin1.git;destsuffix=<local-path>;name=plugin1;protocol=https",
            "git://git.example.com/foo/foo-plugin1.git;name=plugin1;protocol=https;destsuffix=/home/user/poky/build/tmp/work/core2-64-poky-linux/foo/0.0.1/foo-0.0.1/plugins/1" :
                "git://git.example.com/foo/foo-plugin1.git;name=plugin1;protocol=https;destsuffix=<local-path>"
        }
        for src_uri, clean_src_uri in src_uris.items():
            self.assertEqual(
                bb.trace.unpack.get_clean_src_uri(src_uri), clean_src_uri)

    def test_get_clean_src_uri_from_src_uri_with_abs_path_in_url_path(self):
        src_uris = {
            "file:///home/user/meta-foo/foo/foo_fix.patch;subdir=foo":
                "file://<local-path>;subdir=foo",
            "npmsw:///home/user/meta-example/npm-shrinkwrap.json":
                "npmsw://<local-path>"
        }
        for src_uri, clean_src_uri in src_uris.items():
            self.assertEqual(
                bb.trace.unpack.get_clean_src_uri(src_uri), clean_src_uri)


class BlameRecipeFileTest(unittest.TestCase):
    # NOTE function bb.trace.unpack.blame_recipe_file() is not being used for now
    # testing it anyway

    class MockDataStore:

        class MockVarHistory:
            def __init__(self):
                self.SRC_URI_varhistory = [{'variable': 'SRC_URI',
                    'file': '/build/test/oe-core/meta/conf/bitbake.conf',
                    'line': 721,
                    'op': 'append',
                    'detail': '    APACHE_MIRROR     CPAN_MIRROR     DEBIAN_MIRROR     GENTOO_MIRROR     GNOME_GIT     GNOME_MIRROR     GNU_MIRROR     GNUPG_MIRROR     GPE_MIRROR     KERNELORG_MIRROR     SAMBA_MIRROR     SAVANNAH_GNU_MIRROR     SAVANNAH_NONGNU_MIRROR     SOURCEFORGE_MIRROR     XLIBS_MIRROR     XORG_MIRROR ',
                    'flag': 'vardepsexclude'},
                    {'parsing': True,
                    'variable': 'SRC_URI',
                    'file': '/build/test/oe-core/meta/conf/bitbake.conf',
                    'line': 735,
                    'op': 'set',
                    'detail': ''},
                    {'variable': 'SRC_URI',
                    'file': '/build/test/oe-core/meta/conf/documentation.conf',
                    'line': 393,
                    'op': 'set',
                    'detail': 'The list of source files - local or remote. This variable tells the OpenEmbedded build system what bits to pull in for the build and how to pull them in.',
                    'flag': 'doc'},
                    {'parsing': True,
                    'variable': 'SRC_URI',
                    'file': '/build/test/oe-core/../meta-arm/meta-arm/recipes-security/optee/optee-client.inc',
                    'line': 14,
                    'op': 'set',
                    'detail': '     git://github.com/OP-TEE/optee_client.git;branch=master;protocol=https     file://tee-supplicant.service     file://tee-supplicant.sh '},
                    {'parsing': True,
                    'variable': 'SRC_URI',
                    'file': '/build/test/oe-core/../meta-ledge-secure/meta-ledge-secure/recipes-security/optee/optee-client_3.16.0.bbappend',
                    'line': 12,
                    'op': ':append',
                    'detail': ' file://0001-libckteec-add-support-for-ECDH-derive.patch \tfile://0002-tee-supplicant-introduce-struct-tee_supplicant_param.patch \tfile://0003-tee-supplicant-refactor-argument-parsing-in-main.patch \tfile://0004-tee-supplicant-rpmb-introduce-readn-wrapper-to-the-r.patch \tfile://0005-tee-supplicant-rpmb-read-CID-in-one-go.patch \tfile://0006-tee-supplicant-add-rpmb-cid-command-line-option.patch \tfile://create-tee-supplicant-env         file://optee-udev.rules \t'}]

            def variable(self, var):
                if var == "SRC_URI":
                    return self.SRC_URI_varhistory

        def __init__(self):
            self.SRC_URI = '     git://github.com/OP-TEE/optee_client.git;branch=master;protocol=https     file://tee-supplicant.service     file://tee-supplicant.sh  file://0001-libckteec-add-support-for-ECDH-derive.patch \tfile://0002-tee-supplicant-introduce-struct-tee_supplicant_param.patch \tfile://0003-tee-supplicant-refactor-argument-parsing-in-main.patch \tfile://0004-tee-supplicant-rpmb-introduce-readn-wrapper-to-the-r.patch \tfile://0005-tee-supplicant-rpmb-read-CID-in-one-go.patch \tfile://0006-tee-supplicant-add-rpmb-cid-command-line-option.patch \tfile://create-tee-supplicant-env         file://optee-udev.rules \t'
            self.varhistory = self.MockVarHistory()

        def getVar(self, var):
            if var == "SRC_URI":
                return self.SRC_URI

    def test_get_src_uri_recipe_file_bbappend(self):
        d = self.MockDataStore()
        recipe_file = bb.trace.unpack.blame_recipe_file("file://0001-libckteec-add-support-for-ECDH-derive.patch", d)
        self.assertEqual(recipe_file, "/build/test/oe-core/../meta-ledge-secure/meta-ledge-secure/recipes-security/optee/optee-client_3.16.0.bbappend")

    def test_get_src_uri_recipe_file_set_in_inc(self):
        d = self.MockDataStore()
        recipe_file = bb.trace.unpack.blame_recipe_file("file://tee-supplicant.sh", d)
        self.assertEqual(recipe_file, "/build/test/oe-core/../meta-arm/meta-arm/recipes-security/optee/optee-client.inc")


class GetDownloadLocationAndRelpathTest(unittest.TestCase):

    # TODO add test with a git remote pointing to repo tool manifest

    def test_get_dl_loc_for_dir_in_git_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            create_file(tmpdir / "repo/README", "hello")
            create_file(tmpdir / "repo/doc/help.txt", "help")
            git_dir = tmpdir/"repo"
            subprocess.check_output(["git", "init"], cwd=git_dir)
            subprocess.check_output(["git", "add", "-A"], cwd=git_dir)
            subprocess.check_output(["git", "commit", "-m", "'initial commit'"], cwd=git_dir)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_dir).decode().strip("\n")
            download_location, relpath = bb.trace.unpack.get_dl_loc(tmpdir/"repo/doc")
            self.assertEqual((download_location, relpath), (None, None)) # no origin

            os.rename(tmpdir/"repo/.git", tmpdir/"repo.git")
            subprocess.check_output(["rm", "-Rf", "repo"], cwd=tmpdir)
            subprocess.check_output(["git", "clone", "repo.git"], cwd=tmpdir, stderr=subprocess.DEVNULL)
            download_location, relpath = bb.trace.unpack.get_dl_loc(tmpdir/"repo/doc")
            self.assertEqual(download_location, "git+%s@%s" % (tmpdir/"repo.git", head))
            self.assertEqual(relpath, "doc")

            download_location, relpath = bb.trace.unpack.get_dl_loc(git_dir)
            self.assertEqual(download_location, "git+%s@%s" % (tmpdir/"repo.git", head))
            self.assertEqual(relpath, "")

            create_file(tmpdir/"repo/LICENSE", "CC-0")
            subprocess.check_output(["git", "add", "LICENSE"], cwd=git_dir)
            subprocess.check_output(["git", "commit", "-m", "'add license'"], cwd=git_dir)
            download_location, relpath = bb.trace.unpack.get_dl_loc(git_dir)
            self.assertEqual((download_location, relpath), (None, None))

    def test_get_dl_loc_on_file_with_no_git_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            create_file(tmpdir/"README", "hello")
            download_location, relpath = bb.trace.unpack.get_dl_loc(tmpdir)
            self.assertEqual((download_location, relpath), (None, None))


class IsInCurrentBranchTest(unittest.TestCase):

    def get_untracked_new_and_modified_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            create_file(tmpdir / "repo/README", "hello")
            create_file(tmpdir / "repo/doc/help.txt", "help")
            git_dir = tmpdir/"repo"
            subprocess.check_output(["git", "init"], cwd=git_dir)
            subprocess.check_output(["git", "add", "-A"], cwd=git_dir)
            subprocess.check_output(["git", "commit", "-m", "'initial commit'"], cwd=git_dir)

            # modified
            create_file(tmpdir / "repo/README", "hello there")
            # untracked
            create_file(tmpdir / "repo/test/test.txt", "test")
            # staged, uncommitted
            create_file(tmpdir / "repo/test/test2.txt", "test2")
            subprocess.check_output(["git", "add", "test/test2.txt"], cwd=git_dir)

            untracked_new_and_modified_files = bb.trace.unpack.get_get_untracked_new_and_modified_files(git_dir)

            self.assertFalse("doc/help.txt" in untracked_new_and_modified_files)
            self.assertTrue("README" in untracked_new_and_modified_files)
            self.assertTrue("test/test.txt" in untracked_new_and_modified_files)
            self.assertTrue("test/test2.txt" in untracked_new_and_modified_files)


class TraceUnpackIntegrationTest(unittest.TestCase):

    meta_repos = [(
        "git://git.yoctoproject.org/poky",
        "langdale",
        "yocto-4.1.3",
        "2023-03-05"
    ),(
        "git://git.openembedded.org/meta-openembedded",
        "langdale",
        "b5b732876da1885ecbab2aa45f80d7a3086c5262",
        ""
    )]

    @classmethod
    @skipIfNoNetwork()
    def setUpClass(cls):
        cls.meta_tempdir = tempfile.mkdtemp(prefix="meta-")
        for repo, branch, commit, shallow_since in cls.meta_repos:
            cmd = "git clone"
            if shallow_since:
                cmd += " --shallow-since %s" % shallow_since
            cmd += " --branch %s --single-branch %s" % (branch, repo)
            bb.process.run(cmd, cwd=cls.meta_tempdir)
            basename = re.sub(r"\.git$", "", os.path.basename(repo))
            git_dir = os.path.join(cls.meta_tempdir, basename)
            bb.process.run("git checkout %s" % commit, cwd=git_dir)
        cls.tempdir = tempfile.mkdtemp(prefix="bitbake-trace-")
        cls.dldir = os.path.join(cls.tempdir, "download")
        os.mkdir(cls.dldir)

    @classmethod
    @skipIfNoNetwork()
    def tearDownClass(cls):
        if os.environ.get("BB_TMPDIR_NOCLEAN") == "yes":
            print("Not cleaning up %s. Please remove manually." % cls.meta_tempdir)
            print("Not cleaning up %s. Please remove manually." % cls.tempdir)
        else:
            bb.process.run('chmod u+rw -R %s' % cls.meta_tempdir)
            bb.utils.prunedir(cls.meta_tempdir)
            bb.process.run('chmod u+rw -R %s' % cls.tempdir)
            bb.utils.prunedir(cls.tempdir)

    def run_do_unpack(self, var, var_flags, is_go=False):
        self.d = bb.data.init()
        self.d.setVar("DL_DIR", self.dldir)
        for var_name, value in var.items():
            self.d.setVar(var_name, value)
        for var_name, flags in var_flags.items():
            for flag_name, flag_value in flags.items():
                self.d.setVarFlag(var_name, flag_name, flag_value)
        bb.utils.mkdirhier(self.d.getVar("S"))
        bb.utils.mkdirhier(self.d.getVar("WORKDIR") + "/temp")
        fetcher = bb.fetch2.Fetch(None, self.d)
        fetcher.download()
        if is_go: # simulate go_do_unpack
            for url in fetcher.urls:
                if fetcher.ud[url].type == 'git':
                    if fetcher.ud[url].parm.get('destsuffix') is None:
                        s_dirname = os.path.basename(self.d.getVar('S'))
                        fetcher.ud[url].parm['destsuffix'] = os.path.join(
                            s_dirname, 'src', self.d.getVar('GO_IMPORT')) + '/'
        fetcher.unpack(self.d.getVar("WORKDIR"))

    def get_trace_data_and_expected_trace_data(self):
        json_file = "%s-%s.unpack.trace.json.zst" % (self.d.getVar("PN"), self.d.getVar("PV"))
        path = os.path.join(self.d.getVar("WORKDIR"), "temp", json_file)
        with bb.compress.zstd.open(path, "rt", encoding="utf-8", num_threads=1) as f:
            td = json.load(f)
        this_dir = os.path.dirname(os.path.abspath(__file__))
        testdata_path =  os.path.join(this_dir, "trace-testdata", json_file)
        with bb.compress.zstd.open(testdata_path, "rt", encoding="utf-8", num_threads=1) as f:
            expected_td = json.load(f)
        return td, expected_td

    @skipIfNoNetwork()
    def test_bzip2_case(self):
        """ 1) check if https, git and file src uris are correctly traced
            2) local files configure.ac and Makefile.am from poky/meta layer are
               added to bzip2 source dir (${WORKDIR}/bzip2-1.0.8/) through
               file:// src uris with subdir param: check if their real upstream
               source is correctly identified
            3) SRC_URI contains variables to be expanded: check if the
               unexpanded src uris are correctly identified
        """
        var = {
            "PN": "bzip2",
            "BPN": "bzip2",
            "PV": "1.0.8",
            "BP": "${BPN}-${PV}",
            "SRC_URI":  """https://sourceware.org/pub/${BPN}/${BPN}-${PV}.tar.gz
                           git://sourceware.org/git/bzip2-tests.git;name=bzip2-tests;branch=master
                           file://configure.ac;subdir=${BP}
                           file://Makefile.am;subdir=${BP}
                           file://run-ptest
                        """,
            "SRCREV_bzip2-tests": "f9061c030a25de5b6829e1abf373057309c734c0",
            "FILE": self.meta_tempdir+"/poky/meta/recipes-extended/bzip2/bzip2_1.0.8.bb",
            "FILE_DIRNAME": "${@os.path.dirname(d.getVar('FILE', False))}",
            "FILESPATH": '${FILE_DIRNAME}/${BP}:${FILE_DIRNAME}/${BPN}:${FILE_DIRNAME}/files',
            "WORKDIR": self.tempdir+"/work/core2-64-poky-linux/${PN}/${PV}-r0",
            "S": "${WORKDIR}/${BP}",
            "BBLAYERS": self.meta_tempdir+"/poky/meta",
        }
        var_flags = {
            "SRC_URI": {
                "md5sum": "67e051268d0c475ea773822f7500d0e5",
                "sha256sum": "ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269"
            }
        }
        self.run_do_unpack(var, var_flags)
        td, expected_td =  self.get_trace_data_and_expected_trace_data()
        self.assertEqual(td, expected_td)

    @skipIfNoNetwork()
    def test_gettext_minimal_native_case(self):
        """ check if file src uri pointing to a directory (aclocal/) is
            correctly handled"""
        var = {
            "PN": "gettext-minimal-native",
            "PV": "0.21",
            "BPN": "gettext-minimal",
            "BP": "${BPN}-${PV}",
            "SRC_URI": """file://aclocal/
                          file://config.rpath
                          file://Makefile.in.in
                          file://remove-potcdate.sin
                          file://COPYING
                       """,
            "FILE": self.meta_tempdir+"/poky/meta/recipes-core/gettext/gettext-minimal-native_0.21.1.bb",
            "FILE_DIRNAME": "${@os.path.dirname(d.getVar('FILE', False))}",
            "FILESPATH": '${FILE_DIRNAME}/${BP}:${FILE_DIRNAME}/${BPN}:${FILE_DIRNAME}/files',
            "WORKDIR": self.tempdir+"/work/x86_64-linux/${PN}/${PV}-r0",
            "S": "${WORKDIR}",
            "BBLAYERS": self.meta_tempdir+"/poky/meta",
        }
        var_flags = {}
        self.run_do_unpack(var, var_flags)
        td, expected_td =  self.get_trace_data_and_expected_trace_data()
        self.assertEqual(td, expected_td)

    @skipIfNoNetwork()
    def test_python_cryptography_case(self):
        """ 1) check if crate:// src_uris are handled correctly (download
               location should be the corresponding https download url)
            2) check if package checksum data is handled correctly (we have
               multiple SRC_URI entries supporting checksums here, but the
               checksum var flag set in the recipe refers only to the first
               found entry)
        """
        var = {
            "PN": "python3-cryptography",
            "PV": "37.0.4",
            "BPN": "python3-cryptography",
            "BP": "${BPN}-${PV}",
            "PYPI_SRC_URI": "https://files.pythonhosted.org/packages/source/c/cryptography/cryptography-37.0.4.tar.gz",
            "SRC_URI": """
                ${PYPI_SRC_URI}
                file://run-ptest
                file://check-memfree.py
                file://0001-Cargo.toml-specify-pem-version.patch
                file://0002-Cargo.toml-edition-2018-2021.patch
                file://0001-pyproject.toml-remove-benchmark-disable-option.patch
                crate://crates.io/Inflector/0.11.4
                crate://crates.io/aliasable/0.1.3
                crate://crates.io/asn1/0.8.7
                crate://crates.io/asn1_derive/0.8.7
                crate://crates.io/autocfg/1.1.0
                crate://crates.io/base64/0.13.0
                crate://crates.io/bitflags/1.3.2
                crate://crates.io/cfg-if/1.0.0
                crate://crates.io/chrono/0.4.19
                crate://crates.io/indoc-impl/0.3.6
                crate://crates.io/indoc/0.3.6
                crate://crates.io/instant/0.1.12
                crate://crates.io/lazy_static/1.4.0
                crate://crates.io/libc/0.2.124
                crate://crates.io/lock_api/0.4.7
                crate://crates.io/num-integer/0.1.44
                crate://crates.io/num-traits/0.2.14
                crate://crates.io/once_cell/1.10.0
                crate://crates.io/ouroboros/0.15.0
                crate://crates.io/ouroboros_macro/0.15.0
                crate://crates.io/parking_lot/0.11.2
                crate://crates.io/parking_lot_core/0.8.5
                crate://crates.io/paste-impl/0.1.18
                crate://crates.io/paste/0.1.18
                crate://crates.io/pem/1.0.2
                crate://crates.io/proc-macro-error-attr/1.0.4
                crate://crates.io/proc-macro-error/1.0.4
                crate://crates.io/proc-macro-hack/0.5.19
                crate://crates.io/proc-macro2/1.0.37
                crate://crates.io/pyo3-build-config/0.15.2
                crate://crates.io/pyo3-macros-backend/0.15.2
                crate://crates.io/pyo3-macros/0.15.2
                crate://crates.io/pyo3/0.15.2
                crate://crates.io/quote/1.0.18
                crate://crates.io/redox_syscall/0.2.13
                crate://crates.io/scopeguard/1.1.0
                crate://crates.io/smallvec/1.8.0
                crate://crates.io/stable_deref_trait/1.2.0
                crate://crates.io/syn/1.0.91
                crate://crates.io/unicode-xid/0.2.2
                crate://crates.io/unindent/0.1.8
                crate://crates.io/version_check/0.9.4
                crate://crates.io/winapi-i686-pc-windows-gnu/0.4.0
                crate://crates.io/winapi-x86_64-pc-windows-gnu/0.4.0
                crate://crates.io/winapi/0.3.9
            """,
            "FILE": self.meta_tempdir+"/poky/meta/recipes-devtools/python/python3-cryptography_37.0.4.bb",
            "FILE_DIRNAME": "${@os.path.dirname(d.getVar('FILE', False))}",
            "FILESPATH": '${FILE_DIRNAME}/${BP}:${FILE_DIRNAME}/${BPN}:${FILE_DIRNAME}/files',
            "WORKDIR": self.tempdir+"/work/core2-64-poky-linux/${PN}/${PV}-r0",
            "S": "${WORKDIR}/${BP}",
            "BBLAYERS": self.meta_tempdir+"/poky/meta",
        }
        var_flags = {
            "SRC_URI": {
                "sha256sum": "63f9c17c0e2474ccbebc9302ce2f07b55b3b3fcb211ded18a42d5764f5c10a82",
            }
        }
        self.run_do_unpack(var, var_flags)
        td, expected_td =  self.get_trace_data_and_expected_trace_data()
        self.assertEqual(td, expected_td)

    @skipIfNoNetwork()
    def test_snappy_case(self):
        """check if gitsm src uri is handled correctly"""
        var = {
            "PN": "snappy",
            "PV": "1.1.9",
            "BPN": "snappy",
            "BP": "${BPN}-${PV}",
            "SRC_URI": """
                gitsm://github.com/google/snappy.git;protocol=https;branch=main
                file://0001-Add-inline-with-SNAPPY_ATTRIBUTE_ALWAYS_INLINE.patch
            """,
            "SRCREV": "2b63814b15a2aaae54b7943f0cd935892fae628f",
            "FILE": self.meta_tempdir+"/meta-openembedded/meta-oe/recipes-extended/snappy/snappy_1.1.9.bb",
            "FILE_DIRNAME": "${@os.path.dirname(d.getVar('FILE', False))}",
            "FILESPATH": '${FILE_DIRNAME}/${BP}:${FILE_DIRNAME}/${BPN}:${FILE_DIRNAME}/files',
            "WORKDIR": self.tempdir+"/work/core2-64-poky-linux/${PN}/${PV}-r0",
            "S": "${WORKDIR}/git",
            "BBLAYERS": self.meta_tempdir+"/meta-openembedded/meta-oe",
        }
        var_flags = {}
        self.run_do_unpack(var, var_flags)
        td, expected_td =  self.get_trace_data_and_expected_trace_data()
        self.assertEqual(td, expected_td)

    @skipIfNoNetwork()
    def test_gosu_case(self):
        """ 1) test if src uris pointing to go code are handled correctly
               (mocking go_do_unpack)
            2) test if SRC_URI entries with local absolute path destsuffix param
               are handled correctly
            3) test if symlinks in sources are handled correctly
        """
        var =  {
            "PN": "gosu",
            "PV": "1.14",
            "BPN": "gosu",
            "BP": "${BPN}-${PV}",
            "FILE": self.meta_tempdir+"/meta-openembedded/meta-oe/recipes-support/gosu/gosu_1.14.bb",
            "WORKDIR": self.tempdir+"/work/core2-64-poky-linux/${PN}/${PV}-r0",
            "S": "${WORKDIR}/${BP}",
            "GO_IMPORT": "github.com/tianon/gosu",
            "SRC_URI": """
                git://${GO_IMPORT}.git;branch=master;protocol=https
                git://github.com/opencontainers/runc;name=runc;destsuffix=${S}/src/github.com/opencontainers/runc;branch=main;protocol=https
            """,
            "SRCREV": "9f7cd138a1ebc0684d43ef6046bf723978e8741f",
            "SRCREV_runc": "d7f7b22a85a2387557bdcda125710c2506f8d5c5",
            "BBLAYERS": self.meta_tempdir+"/meta-openembedded/meta-oe",
        }
        var_flags = {}
        self.run_do_unpack(var, var_flags, is_go=True)
        td, expected_td =  self.get_trace_data_and_expected_trace_data()
        self.assertEqual(td, expected_td)

    @skipIfNoNetwork()
    def test_systemd_case(self):
        """check if SRC_URI containing expressions are handled correctly"""
        var = {
            "PN": "systemd",
            "PV": "251.8",
            "BPN": "systemd",
            "BP": "${BPN}-${PV}",
            "SRCBRANCH": "v251-stable",
            "SRCREV": "ae8b249af4acb055f920134f2ac584c4cbc86e3b",
            "SRC_URI": """
                git://github.com/systemd/systemd-stable.git;protocol=https;branch=${SRCBRANCH}
                file://touchscreen.rules
                file://00-create-volatile.conf
                ${@bb.utils.contains('PACKAGECONFIG', 'polkit_hostnamed_fallback', 'file://org.freedesktop.hostname1_no_polkit.conf', '', d)}
                ${@bb.utils.contains('PACKAGECONFIG', 'polkit_hostnamed_fallback', 'file://00-hostnamed-network-user.conf', '', d)}
                file://init
                file://99-default.preset
                file://systemd-pager.sh
                file://0001-binfmt-Don-t-install-dependency-links-at-install-tim.patch
                file://0003-implment-systemd-sysv-install-for-OE.patch
                file://0001-Move-sysusers.d-sysctl.d-binfmt.d-modules-load.d-to-.patch
            """,
            "FILE": self.meta_tempdir+"/poky/meta/recipes-core/systemd/systemd_251.8.bb",
            "FILE_DIRNAME": "${@os.path.dirname(d.getVar('FILE', False))}",
            "FILESPATH": '${FILE_DIRNAME}/${BP}:${FILE_DIRNAME}/${BPN}:${FILE_DIRNAME}/files',
            "WORKDIR": self.tempdir+"/work/core2-64-poky-linux/${PN}/${PV}-r0",
            "S": "${WORKDIR}/git",
            "BBLAYERS": self.meta_tempdir+"/poky/meta",
        }
        var_flags = {}
        self.run_do_unpack(var, var_flags)
        td, expected_td =  self.get_trace_data_and_expected_trace_data()
        self.assertEqual(td, expected_td)

    @skipIfNoNetwork()
    def test_npmsw(self):
        """ 1) test tracing with npmsw fetcher using a small made-up
               npm-shrinkwrap.json file; check if nested non-dedup dependencies
               are handled correctly (some upstream files are replicated in
               multiple path in workdir)
            2) test if files added to existing layer local repos are handled
               correctly (finding local provenance and not upstream provenance)
        """
        this_dir = os.path.dirname(os.path.abspath(__file__))
        npmsw_file = this_dir+"/trace-testdata/npm-shrinkwrap-test.json"
        shutil.copy2(npmsw_file, self.meta_tempdir+"/poky/meta")
        var = {
            "PN": "test_npm",
            "PV": "1.0.0",
            "BPN": "test_npm",
            "BP": "${BPN}-${PV}",
            "NPMSW_PATH": self.meta_tempdir+"/poky/meta",
            "SRC_URI": "npmsw://${NPMSW_PATH}/npm-shrinkwrap-test.json",
            "WORKDIR": self.tempdir+"/work/all-poky-linux/${PN}/${PV}-r0",
            "S": "${WORKDIR}/${BP}",
            "BBLAYERS": self.meta_tempdir+"/poky/meta",
        }
        var_flags = {}
        self.run_do_unpack(var, var_flags)
        td, expected_td =  self.get_trace_data_and_expected_trace_data()
        self.assertEqual(td, expected_td)


if __name__ == '__main__':
    unittest.main()