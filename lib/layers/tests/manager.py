# Copyright (C) 2017 Wind River Systems, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

import unittest
import tempfile
import os
import bb

from layers import manager

import logging

class LayersTest(unittest.TestCase):

    def setUp(self):
        self.origdir = os.getcwd()
        self.d = bb.data.init()
        self.tempdir = tempfile.mkdtemp()
        self.dldir = os.path.join(self.tempdir, "download")
        os.mkdir(self.dldir)
        self.d.setVar("DL_DIR", self.dldir)
        self.unpackdir = os.path.join(self.tempdir, "unpacked")
        self.d.setVar("BBLAYERS_FETCH_DIR", self.unpackdir)
        os.mkdir(self.unpackdir)
        persistdir = os.path.join(self.tempdir, "persistdata")
        self.d.setVar("PERSISTENT_DIR", persistdir)
        self.logger = logging.getLogger("BitBake")
        self.d.setVar('BBLAYERS', '')

    def tearDown(self):
        os.chdir(self.origdir)
        if os.environ.get("BB_TMPDIR_NOCLEAN") == "yes":
            print("Not cleaning up %s. Please remove manually." % self.tempdir)
        else:
            bb.utils.prunedir(self.tempdir)

class LayerManagerTest(LayersTest):
    def setUp(self):
        LayersTest.setUp(self)

        self.manager = manager.LayerManager(self.d, None)

    def test_get_bitbake_info(self):
        (bb_remote, bb_branch, bb_rev, bb_path) = self.manager.get_bitbake_info()

        self.assertTrue("://" in bb_remote)

        us = os.path.dirname(__file__) # bitbake/lib/layers/tests
        us = os.path.dirname(us)       # bitbake/lib/layers
        us = os.path.dirname(us)       # bitbake/lib
        us = os.path.dirname(us)       # bitbake

        self.assertEqual(bb_path, us)

    def test_load_bblayers(self):

        self.d.setVar('LAYERSERIES_CORENAMES', 'under_test')

        self.d.setVar('BBFILE_COLLECTIONS', 'test1')
        self.d.appendVar('BBFILE_COLLECTIONS', ' test2')
        self.d.appendVar('BBFILE_COLLECTIONS', ' test3')

        self.d.setVar('BBLAYERS', '%s/test1_layer %s/test2_layer %s/test3_layer'
                              % (self.tempdir, self.tempdir, self.tempdir))

        self.d.setVar('BBLAYERS_LAYERINDEX_NAME_test1', 'oe-test-layer')

        self.d.setVar('LAYERVERSION_test1', '1')
        self.d.setVar('LAYERVERSION_test2', '2')
        self.d.setVar('LAYERVERSION_test3', '3')

        index = self.manager.load_bblayers()

        self.assertEqual(index['branches'][1].get_name(), 'under_test')

        layerBranch = index['layerBranches'][1]
        self.assertEqual(layerBranch.get_collection(), 'test1')
        self.assertEqual(layerBranch.get_version(), '1')
        self.assertEqual(layerBranch.get_layer().get_name(), 'oe-test-layer')

        layerBranch = index['layerBranches'][2]
        self.assertEqual(layerBranch.get_collection(), 'test2')
        self.assertEqual(layerBranch.get_version(), '2')
        self.assertEqual(layerBranch.get_layer().get_name(), 'test2')

        layerBranch = index['layerBranches'][3]
        self.assertEqual(layerBranch.get_collection(), 'test3')
        self.assertEqual(layerBranch.get_version(), '3')
        self.assertEqual(layerBranch.get_layer().get_name(), 'test3')

    def test_clone_directory(self):
        self.assertEqual(self.manager.get_clone_directory('git://foo/foobar'),
                         os.path.join(self.unpackdir, 'foobar'))

    if os.environ.get("BB_SKIP_NETTESTS") == "yes":
        print("Unset BB_SKIP_NETTESTS to run network tests")
    else:
        def test_fetcher(self):
            from collections import OrderedDict

            from layers.layerindex import Branch, LayerItem, LayerBranch

            branchId = 0
            layerItemId = 0
            layerBranchId = 0

            index = {}
            index['branches'] = {}
            index['layerItems'] = {}
            index['layerBranches'] = {}

            branchId += 1
            index['branches'][branchId] = Branch(index, None)
            index['branches'][branchId].define_data(branchId,
                                        'master', 'master')

            layerItemId +=1
            index['layerItems'][layerItemId] = LayerItem(index, None)
            index['layerItems'][layerItemId].define_data(layerItemId, 'meta-gplv2',
                                        vcs_url='git://git.yoctoproject.org/meta-gplv2')

            layerBranchId +=1
            index['layerBranches'][layerBranchId] = LayerBranch(index, None)
            index['layerBranches'][layerBranchId].define_data(layerBranchId,
                                        'gplv2', '1', layerItemId, branchId)


            dependencies = OrderedDict()
            layerBranch = index['layerBranches'][layerBranchId]
            dependencies[layerBranch.get_layer().get_name()] = [layerBranch]

            self.d.setVar('BBLAYERS_FETCHER_TYPE', 'fetcher')
            self.manager.setup(dependencies)
            self.manager.fetch()
            self.manager.unpack()

            fetchplugin = self.manager.get_plugin(self.manager.index_fetcher)
            newlayers = fetchplugin.get_new_layers()

            self.assertFalse(not newlayers)

            self.assertTrue(os.path.isdir(newlayers[0]))
            self.assertTrue(os.path.isfile(os.path.join(newlayers[0],'conf/layer.conf')))
