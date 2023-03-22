
# Copyright (C) 2023 Alberto Pianon <pianon@array.eu>
#
# SPDX-License-Identifier: GPL-2.0-only
#

import os
import re
import unittest
import tempfile
from pathlib import Path
import subprocess

import bb

def create_src_dst(tmpdir):
    src_dir = os.path.join(tmpdir, "src/")
    dst_dir = os.path.join(tmpdir, "dst/")
    os.makedirs(src_dir)
    os.makedirs(dst_dir)
    return Path(src_dir), Path(dst_dir)

def make_dirname(path):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

def create_file(path, content):
    make_dirname(path)
    with open(path, "w") as f:
        f.write(content)

def create_link(path, target):
    make_dirname(path)
    os.symlink(target, path)

def get_tree(path):
    curdir = os.getcwd()
    os.chdir(path)
    tree = []
    for root, dirs, files in os.walk("."):
        for f in dirs + files:
            tree.append(re.sub(r"^\.\/", "", os.path.join(root, f)))
    os.chdir(curdir)
    return sorted(tree)

def read_file(path):
    with open(path) as f:
        return f.read()

class MoveContentsTest(unittest.TestCase):

    def test_dir_merge_and_file_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)
            create_file(src_dir / "dir/subdir/file.txt", "new")
            create_file(dst_dir / "dir/subdir/file.txt", "old")
            create_file(dst_dir / "dir/subdir/file1.txt", "old")
            bb.trace.unpack_base.move_contents(src_dir, dst_dir)
            expected_dst_tree = [
                "dir",
                "dir/subdir",
                "dir/subdir/file.txt",
                "dir/subdir/file1.txt"
            ]
            self.assertEqual(get_tree(src_dir), [])
            self.assertEqual(get_tree(dst_dir), expected_dst_tree)
            self.assertEqual(read_file(dst_dir / "dir/subdir/file.txt"), "new")
            self.assertEqual(read_file(dst_dir / "dir/subdir/file1.txt"), "old")

    def test_file_vs_symlink_conflicts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)

            create_file(src_dir / "dir/subdir/fileA.txt", "new")
            create_file(src_dir / "dir/fileB.txt", "new")
            create_link(src_dir / "file.txt", "dir/subdir/fileA.txt")

            create_file(dst_dir / "dir/subdir/fileA.txt", "old")
            create_link(dst_dir / "dir/fileB.txt", "subdir/fileA.txt")
            create_file(dst_dir / "file.txt", "old")

            bb.trace.unpack_base.move_contents(src_dir, dst_dir)
            self.assertEqual(get_tree(src_dir), [])
            self.assertTrue(os.path.islink(dst_dir / "file.txt"))
            self.assertEqual(
                os.readlink(dst_dir / "file.txt"),
                "dir/subdir/fileA.txt"
            )
            self.assertFalse(os.path.islink(dst_dir / "dir/fileB.txt"))
            self.assertEqual(read_file(dst_dir / "dir/fileB.txt"), "new")

    def test_dir_vs_file_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)
            create_file(src_dir / "items/item0/content.txt", "hello")
            create_file(dst_dir / "items/item0", "there")
            bb.trace.unpack_base.move_contents(src_dir, dst_dir)
            self.assertEqual(get_tree(src_dir), [])
            self.assertTrue(os.path.isdir(dst_dir / "items/item0"))
            self.assertEqual(
                read_file(dst_dir / "items/item0/content.txt"), "hello")

    def test_dir_vs_symlink_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)
            create_file(src_dir / "items/item0/content.txt", "hello")
            create_file(dst_dir / "items/item1/content.txt", "there")
            create_link(dst_dir / "items/item0", "item1")
            bb.trace.unpack_base.move_contents(src_dir, dst_dir)
            self.assertEqual(get_tree(src_dir), [])
            self.assertFalse(os.path.islink(dst_dir / "items/item0"))
            self.assertEqual(
                read_file(dst_dir / "items/item0/content.txt"), "hello")
            self.assertEqual(
                read_file(dst_dir / "items/item1/content.txt"), "there")

    def test_symlink_vs_empty_dir_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)
            create_file(src_dir / "items/item1/content.txt", "there")
            create_link(src_dir / "items/item0", "item1")
            os.makedirs(dst_dir / "items/item0")
            bb.trace.unpack_base.move_contents(src_dir, dst_dir)
            self.assertEqual(get_tree(src_dir), [])
            self.assertTrue(os.path.islink(dst_dir / "items/item0"))
            self.assertEqual(read_file(dst_dir / "items/item0/content.txt"), "there")

    def test_symlink_vs_nonempty_dir_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)
            create_file(src_dir / "items/item1/content.txt", "there")
            create_link(src_dir / "items/item0", "item1")
            create_file(dst_dir / "items/item0/content.txt", "hello")
            with self.assertRaises(bb.trace.TraceException) as context:
                bb.trace.unpack_base.move_contents(src_dir, dst_dir)

    def test_file_vs_empty_dir_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)
            create_file(src_dir / "items/item0", "test")
            os.makedirs(dst_dir / "items/item0")
            bb.trace.unpack_base.move_contents(src_dir, dst_dir)
            self.assertEqual(get_tree(src_dir), [])
            self.assertTrue(os.path.isfile(dst_dir/ "items/item0"))

    def test_file_vs_nonempty_dir_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)
            create_file(src_dir / "items/item0", "test")
            create_file(dst_dir / "items/item0/content.txt", "test")
            with self.assertRaises(bb.trace.TraceException) as context:
                bb.trace.unpack_base.move_contents(src_dir, dst_dir)

    def test_git_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir, dst_dir = create_src_dst(tmpdir)
            git_repo = src_dir / "src/my_git_repo"
            create_file(git_repo / "foo.txt", "hello")
            subprocess.check_output(["git", "init"], cwd=git_repo)
            create_file(dst_dir / "src/my_git_repo/content.txt", "there")
            bb.trace.unpack_base.move_contents(src_dir, dst_dir)
            self.assertFalse(
                os.path.exists(dst_dir / "src/my_git_repo/content.txt"))
                # git clone dir should be pruned if already existing
            self.assertEqual(
                read_file(dst_dir / "src/my_git_repo/foo.txt"), "hello")
            self.assertTrue(os.path.isdir(dst_dir / "src/my_git_repo/.git"))


class FindAllFilesAndLinksTest(unittest.TestCase):

    def test_findall_files_and_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            files = {
                str(tmpdir/"foo/example/example.txt"): "ciao",
                str(tmpdir/"foo/foo.txt"): "foo",
                str(tmpdir/"foo/foo2.txt"): "foo2",
                str(tmpdir/"README"): "hello",
            }
            ignored = {
                str(tmpdir/".git"): "fake",
                str(tmpdir/"foo/.git/dummy"): "dummy"
            }
            allfiles = files.copy()
            allfiles.update(ignored)
            links = {
                str(tmpdir/"example"): "foo/example", # link to dir
                str(tmpdir/"example.txt"): "foo/example/example.txt", # link to file
            }
            for path, content in allfiles.items():
                create_file(path, content)
            for path, target in links.items():
                create_link(path, target)
            res_files, res_links = bb.trace.unpack_base.findall_files_and_links(tmpdir, exclude=['.git'])
            self.assertEqual(res_files, sorted(list(files.keys())))
            self.assertEqual(res_links, sorted(list(links.keys())))


if __name__ == '__main__':
    unittest.main()
