# Copyright (C) 2016-2017 Wind River Systems, Inc.
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

import logging
import json

from collections import OrderedDict, defaultdict

from urllib.parse import unquote

import layers.layerindex

from layers.layerindex.common import IndexPlugin
from layers.layerindex.common import LayerIndexError
from layers.layerindex.common import add_element

from layers.manager import _get_manager

logger = logging.getLogger('BitBake.layerindex.cooker')

import bb.utils

def plugin_init(plugins):
    return CookerPlugin()

class CookerPlugin(IndexPlugin):
    def __init__(self):
        self.type = "cooker"
        self.server_connection = None
        self.ui_module = None
        self.server = None

    def load_index(self, ud, load):
        """
            Fetches layer information from a build configuration.

            The return value is a dictionary containing API,
            layer, branch, dependency, recipe, machine, distro, information.

            ud path is ignored.
        """

        if ud.type != 'file':
            raise bb.fetch2.FetchError('%s is not a supported protocol, only file, http and https are support.')

        manager = _get_manager()
        if not manager:
            raise Exception('layer manager object has not been setup!')

        localdata = self.lindex.data.createCopy()
        # If the URL passed in branches, then we fake it...
        if 'branch' in ud.parm:
            localdata.setVar('LAYERSERIES_CORENAMES', ' '.join(ud.parm['branch'].split(',')))

        lindex = manager.load_bblayers(localdata)

        lindex['CONFIG'] = {}
        lindex['CONFIG']['TYPE'] = self.type
        lindex['CONFIG']['URL'] = ud.url

        if 'desc' in ud.parm:
            lindex['CONFIG']['DESCRIPTION'] = unquote(ud.parm['desc'])
        else:
            lindex['CONFIG']['DESCRIPTION'] = ud.path

        if 'cache' in ud.parm:
            lindex['CONFIG']['CACHE'] = ud.parm['cache']

        if 'branch' in ud.parm:
            lindex['CONFIG']['BRANCH'] = ud.parm['branch']
        else:
            lindex['CONFIG']['BRANCH'] = localdata.getVar('LAYERSERIES_CORENAMES') or "HEAD"

        # ("layerDependencies", layerindex.LayerDependency)
        layerDependencyId = 0
        if "layerDependencies" in load.split():
            lindex['layerDependencies'] = {}
            for layerBranchId in lindex['layerBranches']:
                branchName = lindex['layerBranches'][layerBranchId].get_branch().get_name()
                collection = lindex['layerBranches'][layerBranchId].get_collection()

                def add_dependency(layerDependencyId, lindex, deps, required):
                    try:
                        depDict = bb.utils.explode_dep_versions2(deps)
                    except bb.utils.VersionStringException as vse:
                        bb.fatal('Error parsing LAYERDEPENDS_%s: %s' % (c, str(vse)))

                    for dep, oplist in list(depDict.items()):
                        # We need to search ourselves, so use the _ version...
                        depLayerBranch = self.lindex._find_collection(lindex, dep, branch=branchName)
                        if not depLayerBranch:
                            # Missing dependency?!
                            logger.error('Missing dependency %s (%s)' % (dep, branchName))
                            continue

                        # We assume that the oplist matches...
                        layerDependencyId += 1
                        layerDependency = layers.layerindex.LayerDependency(lindex, None)
                        layerDependency.define_data(id=layerDependencyId,
                                        required=required, layerbranch=layerBranchId,
                                        dependency=depLayerBranch.get_layer_id())

                        logger.debug(1, '%s requires %s' % (layerDependency.get_layer().get_name(), layerDependency.get_dependency_layer().get_name()))
                        lindex = add_element("layerDependencies", [layerDependency], lindex)

                    return layerDependencyId

                deps = localdata.getVar("LAYERDEPENDS_%s" % collection)
                if deps:
                    layerDependencyId = add_dependency(layerDependencyId, lindex, deps, True)

                deps = localdata.getVar("LAYERRECOMMENDS_%s" % collection)
                if deps:
                    layerDependencyId = add_dependency(layerDependencyId, lindex, deps, False)

        # Need to load recipes here (requires cooker access)
        recipeId = 0
        ## TODO: NOT IMPLEMENTED
        # The code following this is an example of what needs to be
        # implemented.  However, it does not work as-is.
        if False and 'recipes' in load.split():
            lindex['recipes'] = {}

            ret = self.ui_module.main(self.server_connection.connection, self.server_connection.events, config_params)

            all_versions = self._run_command('allProviders')

            all_versions_list = defaultdict(list, all_versions)
            for pn in all_versions_list:
                for ((pe, pv, pr), fpath) in all_versions_list[pn]:
                    realfn = bb.cache.virtualfn2realfn(fpath)

                    filepath = os.path.dirname(realfn[0])
                    filename = os.path.basename(realfn[0])

                    # This is all HORRIBLY slow, and likely unnecessary
                    #dscon = self._run_command('parseRecipeFile', fpath, False, [])
                    #connector = myDataStoreConnector(self, dscon.dsindex)
                    #recipe_data = bb.data.init()
                    #recipe_data.setVar('_remote_data', connector)

                    #summary = recipe_data.getVar('SUMMARY')
                    #description = recipe_data.getVar('DESCRIPTION')
                    #section = recipe_data.getVar('SECTION')
                    #license = recipe_data.getVar('LICENSE')
                    #homepage = recipe_data.getVar('HOMEPAGE')
                    #bugtracker = recipe_data.getVar('BUGTRACKER')
                    #provides = recipe_data.getVar('PROVIDES')

                    layer = bb.utils.get_file_layer(realfn[0], self.config_data)

                    depBranchId = collection_layerbranch[layer]

                    recipeId += 1
                    recipe = layerindex.Recipe(lindex, None)
                    recipe.define_data(id=recipeId,
                                   filename=filename, filepath=filepath,
                                   pn=pn, pv=pv,
                                   summary=pn, description=pn, section='?',
                                   license='?', homepage='?', bugtracker='?',
                                   provides='?', bbclassextend='?', inherits='?',
                                   blacklisted='?', layerbranch=depBranchId)

                    lindex = addElement("recipes", [recipe], lindex)

        # ("machines", layerindex.Machine)
        machineId = 0
        if 'machines' in load.split():
            lindex['machines'] = {}

            for layerBranchId in lindex['layerBranches']:
                # load_bblayers uses the description to cache the actual path...
                machine_path = lindex['layerBranches'][layerBranchId].getDescription()
                machine_path = os.path.join(machine_path, 'conf/machine')
                if os.path.isdir(machine_path):
                    for (dirpath, _, filenames) in os.walk(machine_path):
                        # Ignore subdirs...
                        if not dirpath.endswith('conf/machine'):
                            continue
                        for fname in filenames:
                            if fname.endswith('.conf'):
                                machineId += 1
                                machine = layers.layerindex.Machine(lindex, None)
                                machine.define_data(id=machineId, name=fname[:-5],
                                                    description=fname[:-5],
                                                    layerbranch=collection_layerbranch[entry])

                                lindex = add_element("machines", [machine], lindex)

        # ("distros", layerindex.Distro)
        distroId = 0
        if 'distros' in load.split():
            lindex['distros'] = {}

            for layerBranchId in lindex['layerBranches']:
                # load_bblayers uses the description to cache the actual path...
                distro_path = lindex['layerBranches'][layerBranchId].getDescription()
                distro_path = os.path.join(distro_path, 'conf/distro')
                if os.path.isdir(distro_path):
                    for (dirpath, _, filenames) in os.walk(distro_path):
                        # Ignore subdirs...
                        if not dirpath.endswith('conf/distro'):
                            continue
                        for fname in filenames:
                            if fname.endswith('.conf'):
                                distroId += 1
                                distro = layers.layerindex.Distro(lindex, None)
                                distro.define_data(id=distroId, name=fname[:-5],
                                                    description=fname[:-5],
                                                    layerbranch=collection_layerbranch[entry])

                                lindex = add_element("distros", [distro], lindex)

        return lindex
