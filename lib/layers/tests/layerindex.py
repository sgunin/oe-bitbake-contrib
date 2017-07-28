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

from layers import layerindex

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
        os.mkdir(self.unpackdir)
        persistdir = os.path.join(self.tempdir, "persistdata")
        self.d.setVar("PERSISTENT_DIR", persistdir)
        self.logger = logging.getLogger("BitBake")

    def tearDown(self):
        os.chdir(self.origdir)
        if os.environ.get("BB_TMPDIR_NOCLEAN") == "yes":
            print("Not cleaning up %s. Please remove manually." % self.tempdir)
        else:
            bb.utils.prunedir(self.tempdir)

class LayerObjectTest(LayersTest):
    def setUp(self):
        from layers.layerindex import Branch, LayerItem, LayerBranch, LayerDependency, Recipe, Machine, Distro

        LayersTest.setUp(self)

        self.index = {}

        branchId = 0
        layerItemId = 0
        layerBranchId = 0
        layerDependencyId = 0
        recipeId = 0
        machineId = 0
        distroId = 0

        self.index['branches'] = {}
        self.index['layerItems'] = {}
        self.index['layerBranches'] = {}
        self.index['layerDependencies'] = {}
        self.index['recipes'] = {}
        self.index['machines'] = {}
        self.index['distros'] = {}

        branchId += 1
        self.index['branches'][branchId] = Branch(self.index, None)
        self.index['branches'][branchId].define_data(branchId,
                                        'test_branch', 'bb_test_branch')

        layerItemId +=1
        self.index['layerItems'][layerItemId] = LayerItem(self.index, None)
        self.index['layerItems'][layerItemId].define_data(layerItemId, 'test_layerItem',
                                        vcs_url='git://git_test_url/test_layerItem')

        layerBranchId +=1
        self.index['layerBranches'][layerBranchId] = LayerBranch(self.index, None)
        self.index['layerBranches'][layerBranchId].define_data(layerBranchId,
                                        'test_collection', '99', layerItemId,
                                        branchId)

        recipeId += 1
        self.index['recipes'][recipeId] = Recipe(self.index, None)
        self.index['recipes'][recipeId].define_data(recipeId, 'test_git.bb',
                                        'recipes-test', 'test', 'git',
                                        layerBranchId)

        machineId += 1
        self.index['machines'][machineId] = Machine(self.index, None)
        self.index['machines'][machineId].define_data(machineId,
                                        'test_machine', 'test_machine',
                                        layerBranchId)

        distroId += 1
        self.index['distros'][distroId] = Distro(self.index, None)
        self.index['distros'][distroId].define_data(distroId,
                                        'test_distro', 'test_distro',
                                        layerBranchId)

        layerItemId +=1
        self.index['layerItems'][layerItemId] = LayerItem(self.index, None)
        self.index['layerItems'][layerItemId].define_data(layerItemId, 'test_layerItem 2',
                                        vcs_url='git://git_test_url/test_layerItem')

        layerBranchId +=1
        self.index['layerBranches'][layerBranchId] = LayerBranch(self.index, None)
        self.index['layerBranches'][layerBranchId].define_data(layerBranchId,
                                        'test_collection_2', '72', layerItemId,
                                        branchId, actual_branch='some_other_branch')

        layerDependencyId += 1
        self.index['layerDependencies'][layerDependencyId] = LayerDependency(self.index, None)
        self.index['layerDependencies'][layerDependencyId].define_data(layerDependencyId,
                                        layerBranchId, 1)

        layerDependencyId += 1
        self.index['layerDependencies'][layerDependencyId] = LayerDependency(self.index, None)
        self.index['layerDependencies'][layerDependencyId].define_data(layerDependencyId,
                                        layerBranchId, 1, required=False)

    def test_branch(self):
        branch = self.index['branches'][1]
        self.assertEqual(branch.get_id(), 1)
        self.assertEqual(branch.get_name(), 'test_branch')
        self.assertEqual(branch.get_short_description(), 'test_branch')
        self.assertEqual(branch.get_bitbake_branch(), 'bb_test_branch')

    def test_layerItem(self):
        layerItem = self.index['layerItems'][1]
        self.assertEqual(layerItem.get_id(), 1)
        self.assertEqual(layerItem.get_name(), 'test_layerItem')
        self.assertEqual(layerItem.get_summary(), 'test_layerItem')
        self.assertEqual(layerItem.get_description(), 'test_layerItem')
        self.assertEqual(layerItem.get_vcs_url(), 'git://git_test_url/test_layerItem')
        self.assertEqual(layerItem.get_vcs_web_url(), None)
        self.assertEqual(layerItem.get_vcs_web_tree_base_url(), None)
        self.assertEqual(layerItem.get_vcs_web_file_base_url(), None)
        self.assertTrue(layerItem.get_updated() != None)

        layerItem = self.index['layerItems'][2]
        self.assertEqual(layerItem.get_id(), 2)
        self.assertEqual(layerItem.get_name(), 'test_layerItem 2')
        self.assertEqual(layerItem.get_summary(), 'test_layerItem 2')
        self.assertEqual(layerItem.get_description(), 'test_layerItem 2')
        self.assertEqual(layerItem.get_vcs_url(), 'git://git_test_url/test_layerItem')
        self.assertEqual(layerItem.get_vcs_web_url(), None)
        self.assertEqual(layerItem.get_vcs_web_tree_base_url(), None)
        self.assertEqual(layerItem.get_vcs_web_file_base_url(), None)
        self.assertTrue(layerItem.get_updated() != None)

    def test_layerBranch(self):
        layerBranch = self.index['layerBranches'][1]
        self.assertEqual(layerBranch.get_id(), 1)
        self.assertEqual(layerBranch.get_collection(), 'test_collection')
        self.assertEqual(layerBranch.get_version(), '99')
        self.assertEqual(layerBranch.get_vcs_subdir(), '')
        self.assertEqual(layerBranch.get_actual_branch(), 'test_branch')
        self.assertTrue(layerBranch.get_updated() != None)
        self.assertEqual(layerBranch.get_layer_id(), 1)
        self.assertEqual(layerBranch.get_branch_id(), 1)
        self.assertEqual(layerBranch.get_layer(), self.index['layerItems'][1])
        self.assertEqual(layerBranch.get_branch(), self.index['branches'][1])

        layerBranch = self.index['layerBranches'][2]
        self.assertEqual(layerBranch.get_id(), 2)
        self.assertEqual(layerBranch.get_collection(), 'test_collection_2')
        self.assertEqual(layerBranch.get_version(), '72')
        self.assertEqual(layerBranch.get_vcs_subdir(), '')
        self.assertEqual(layerBranch.get_actual_branch(), 'some_other_branch')
        self.assertTrue(layerBranch.get_updated() != None)
        self.assertEqual(layerBranch.get_layer_id(), 2)
        self.assertEqual(layerBranch.get_branch_id(), 1)
        self.assertEqual(layerBranch.get_layer(), self.index['layerItems'][2])
        self.assertEqual(layerBranch.get_branch(), self.index['branches'][1])

    def test_layerDependency(self):
        layerDependency = self.index['layerDependencies'][1]
        self.assertEqual(layerDependency.get_id(), 1)
        self.assertEqual(layerDependency.get_layerbranch_id(), 2)
        self.assertEqual(layerDependency.get_layerbranch(), self.index['layerBranches'][2])
        self.assertEqual(layerDependency.get_layer_id(), 2)
        self.assertEqual(layerDependency.get_layer(), self.index['layerItems'][2])
        self.assertTrue(layerDependency.is_required())
        self.assertEqual(layerDependency.get_dependency_id(), 1)
        self.assertEqual(layerDependency.get_dependency_layer(), self.index['layerItems'][1])
        self.assertEqual(layerDependency.get_dependency_layerBranch(), self.index['layerBranches'][1])

        # Previous check used the fall back method.. now use the faster method
        # Create quick lookup layerBranches_layerId_branchId table
        if 'layerBranches' in self.index:
            # Create associated quick lookup indexes
            self.index['layerBranches_layerId_branchId'] = {}
            for layerBranchId in self.index['layerBranches']:
                obj = self.index['layerBranches'][layerBranchId]
                self.index['layerBranches_layerId_branchId']["%s:%s" % (obj.get_layer_id(), obj.get_branch_id())] = obj

        layerDependency = self.index['layerDependencies'][2]
        self.assertEqual(layerDependency.get_id(), 2)
        self.assertEqual(layerDependency.get_layerbranch_id(), 2)
        self.assertEqual(layerDependency.get_layerbranch(), self.index['layerBranches'][2])
        self.assertEqual(layerDependency.get_layer_id(), 2)
        self.assertEqual(layerDependency.get_layer(), self.index['layerItems'][2])
        self.assertFalse(layerDependency.is_required())
        self.assertEqual(layerDependency.get_dependency_id(), 1)
        self.assertEqual(layerDependency.get_dependency_layer(), self.index['layerItems'][1])
        self.assertEqual(layerDependency.get_dependency_layerBranch(), self.index['layerBranches'][1])

    def test_recipe(self):
        recipe = self.index['recipes'][1]
        self.assertEqual(recipe.get_id(), 1)
        self.assertEqual(recipe.get_layerbranch_id(), 1)
        self.assertEqual(recipe.get_layerbranch(), self.index['layerBranches'][1])
        self.assertEqual(recipe.get_layer_id(), 1)
        self.assertEqual(recipe.get_layer(), self.index['layerItems'][1])
        self.assertEqual(recipe.get_filename(), 'test_git.bb')
        self.assertEqual(recipe.get_filepath(), 'recipes-test')
        self.assertEqual(recipe.get_fullpath(), 'recipes-test/test_git.bb')
        self.assertEqual(recipe.get_summary(), "")
        self.assertEqual(recipe.get_description(), "")
        self.assertEqual(recipe.get_section(), "")
        self.assertEqual(recipe.get_pn(), 'test')
        self.assertEqual(recipe.get_pv(), 'git')
        self.assertEqual(recipe.get_license(), "")
        self.assertEqual(recipe.get_homepage(), "")
        self.assertEqual(recipe.get_bugtracker(), "")
        self.assertEqual(recipe.get_provides(), "")
        self.assertTrue(recipe.get_updated() != None)
        self.assertEqual(recipe.get_inherits(), "")

    def test_machine(self):
        machine = self.index['machines'][1]
        self.assertEqual(machine.get_id(), 1)
        self.assertEqual(machine.get_layerbranch_id(), 1)
        self.assertEqual(machine.get_layerbranch(), self.index['layerBranches'][1])
        self.assertEqual(machine.get_layer_id(), 1)
        self.assertEqual(machine.get_layer(), self.index['layerItems'][1])
        self.assertEqual(machine.get_name(), 'test_machine')
        self.assertEqual(machine.get_description(), 'test_machine')
        self.assertTrue(machine.get_updated() != None)

    def test_distro(self):
        distro = self.index['distros'][1]
        self.assertEqual(distro.get_id(), 1)
        self.assertEqual(distro.get_layerbranch_id(), 1)
        self.assertEqual(distro.get_layerbranch(), self.index['layerBranches'][1])
        self.assertEqual(distro.get_layer_id(), 1)
        self.assertEqual(distro.get_layer(), self.index['layerItems'][1])
        self.assertEqual(distro.get_name(), 'test_distro')
        self.assertEqual(distro.get_description(), 'test_distro')
        self.assertTrue(distro.get_updated() != None)


class LayerIndexWebRestApiTest(LayersTest):

    if os.environ.get("BB_SKIP_NETTESTS") == "yes":
        print("Unset BB_SKIP_NETTESTS to run network tests")
    else:
        def setUp(self):
            LayersTest.setUp(self)
            self.lindex = layerindex.LayerIndex(self.d)
            self.lindex.load_layerindex('http://layers.openembedded.org/layerindex/api/;type=restapi;branch=morty', load='layerDependencies')

        def test_layerindex_is_empty(self):
            self.assertFalse(self.lindex.is_empty())

        def test_layerindex_store_file(self):
            self.lindex.store_layerindex('file://%s/file.json;type=restapi' % self.tempdir, self.lindex.lindex[0])

            self.assertTrue(os.path.isfile('%s/file.json' % self.tempdir))

            reload = layerindex.LayerIndex(self.d)
            reload.load_layerindex('file://%s/file.json;type=restapi' % self.tempdir)

            self.assertFalse(reload.is_empty())

            # Calculate layerItems in original index that should NOT be in reload
            layerItemNames = []
            for itemId in self.lindex.lindex[0]['layerItems']:
                layerItemNames.append(self.lindex.lindex[0]['layerItems'][itemId].get_name())

            for layerBranchId in self.lindex.lindex[0]['layerBranches']:
                layerItemNames.remove(self.lindex.lindex[0]['layerBranches'][layerBranchId].get_layer().get_name())

            for itemId in reload.lindex[0]['layerItems']:
                self.assertFalse(reload.lindex[0]['layerItems'][itemId].get_name() in layerItemNames)

            # Compare the original to what we wrote...
            for type in self.lindex.lindex[0]:
                if type == 'apilinks' or \
                   type == 'layerItems' or \
                   type in self.lindex.lindex[0]['CONFIG']['local']:
                    continue
                for id in self.lindex.lindex[0][type]:
                    self.logger.debug(1, "type %s" % (type))

                    self.assertTrue(id in reload.lindex[0][type])

                    self.logger.debug(1, "%s ? %s" % (self.lindex.lindex[0][type][id], reload.lindex[0][type][id]))

                    self.assertEqual(self.lindex.lindex[0][type][id], reload.lindex[0][type][id])

        def test_layerindex_store_split(self):
            self.lindex.store_layerindex('file://%s;type=restapi' % self.tempdir, self.lindex.lindex[0])

            reload = layerindex.LayerIndex(self.d)
            reload.load_layerindex('file://%s;type=restapi' % self.tempdir)

            self.assertFalse(reload.is_empty())

            for type in self.lindex.lindex[0]:
                if type == 'apilinks' or \
                   type == 'layerItems' or \
                   type in self.lindex.lindex[0]['CONFIG']['local']:
                    continue
                for id in self.lindex.lindex[0][type]:
                    self.logger.debug(1, "type %s" % (type))

                    self.assertTrue(id in reload.lindex[0][type])

                    self.logger.debug(1, "%s ? %s" % (self.lindex.lindex[0][type][id], reload.lindex[0][type][id]))

                    self.assertEqual(self.lindex.lindex[0][type][id], reload.lindex[0][type][id])

        def test_dependency_resolution(self):
            # Verify depth first searching...
            (dependencies, invalidnames) = self.lindex.get_dependencies(names='meta-python')

            first = True
            for deplayerbranch in dependencies:
                layerBranch = dependencies[deplayerbranch][0]
                layerDeps = dependencies[deplayerbranch][1:]

                if not first:
                    continue

                first = False

                # Top of the deps should be openembedded-core, since everything depends on it.
                self.assertEquals(layerBranch.get_layer().get_name(), "openembedded-core")

                # meta-python should cause an openembedded-core dependency, if not assert!
                for dep in layerDeps:
                    if dep.get_layer().get_name() == 'meta-python':
                        break
                else:
                    self.assetTrue(False)

                # Only check the first element...
                break
            else:
                if first:
                    # Empty list, this is bad.
                    self.assertTrue(False)

                # Last dep should be the requested item
                layerBranch = dependencies[deplayerbranch][0]
                self.assertEquals(layerBranch.get_layer().get_name(), "meta-python")

        def test_find_collection(self):
            result = self.lindex.find_collection('core')

            self.assertTrue(result != None)

        def test_get_layerbranch(self):
            result = self.lindex.get_layerbranch('openembedded-core')

            self.assertTrue(result != None)
