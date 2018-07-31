# Copyright (C) 2016-2018 Wind River Systems, Inc.
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
import imp
import re

from collections import defaultdict, OrderedDict

import layerindexlib

logger = logging.getLogger('BitBake.bblayerlib')

# Exceptions

class BBLayerLibException(Exception):
    '''BBLayerLib Generic Exception'''
    def __init__(self, message):
         self.msg = message
         Exception.__init__(self, message)

    def __str__(self):
         return self.msg

class BBLayerLibUrlError(BBLayerLibException):
    '''Exception raised when unable to access a URL for some reason'''
    def __init__(self, url, message=""):
        if message:
            msg = "Unable to access url %s: %s" % (url, message)
        else:
            msg = "Unable to access url %s" % url
        self.url = url
        BBLayerLibException.__init__(self, msg)

class BBLayerLibFetchError(BBLayerLibException):
    '''General layerindex fetcher exception when something fails'''
    def __init__(self, url, message=""):
        if message:
            msg = "Unable to fetch url %s: %s" % (url, message)
        else:
            msg = "Unable to fetch url %s" % url
        self.url = url
        BBLayerLibException.__init__(self, msg)


# Interface to managing the bblayers.conf file
class BBLayers():
    def __init__(self, d):
        self.data = d
        self.bblayers = None

    def _run_command(self, command, path, default=None):
        try:
            result, _ = bb.process.run(command, cwd=path)
            result = result.strip()
        except bb.process.ExecutionError:
            result = default
        return result

    def _handle_git_remote(self, remote):
        if "://" not in remote:
            if ':' in remote:
                # This is assumed to be ssh
                remote = "ssh://" + remote
            else:
                # This is assumed to be a file path
                remote = "file://" + remote
        return remote

    def _get_bitbake_info(self):
        """Return a tuple of bitbake information"""

        # Our path SHOULD be .../bitbake/lib/bblayerlib/__init__.py
        bb_path = os.path.dirname(__file__) # .../bitbake/lib/bblayerlib/__init__.py
        bb_path = os.path.dirname(bb_path)  # .../bitbake/lib/bblayerlib
        bb_path = os.path.dirname(bb_path)  # .../bitbake/lib
        bb_path = os.path.dirname(bb_path)  # .../bitbake
        bb_path = self._run_command('git rev-parse --show-toplevel', os.path.dirname(__file__), default=bb_path)
        bb_branch = self._run_command('git rev-parse --abbrev-ref HEAD', bb_path, default="<unknown>")
        bb_rev = self._run_command('git rev-parse HEAD', bb_path, default="<unknown>")
        for remotes in self._run_command('git remote -v', bb_path, default="").split("\n"):
            remote = remotes.split("\t")[1].split(" ")[0]
            if "(fetch)" == remotes.split("\t")[1].split(" ")[1]:
                bb_remote = self._handle_git_remote(remote)
                break
        else:
            bb_remote = self._handle_git_remote(bb_path)

        return (bb_remote, bb_branch, bb_rev, bb_path)

    def load_bblayers(self, branches=None):
        """Load the BBLAYERS and related collection information"""

        if not branches:
            branches = [ 'HEAD' ]

        # Manage the items as a LayerInexObject.. just a bit easier
        self.bblayers = layerindexlib.LayerIndexObj()

        branchId = 0
        self.bblayers.branches = {}

        layerItemId = 0
        self.bblayers.layerItems = {}

        layerBranchId = 0
        self.bblayers.layerBranches = {}

        bblayers = self.data.getVar('BBLAYERS').split()

        if not bblayers:
            # It's blank!  Nothing to process...
            return self.bblayers

        collections = self.data.getVar('BBFILE_COLLECTIONS')
        layerconfs = self.data.varhistory.get_variable_items_files('BBFILE_COLLECTIONS', self.data)
        bbfile_collections = {layer: os.path.dirname(os.path.dirname(path)) for layer, path in layerconfs.items()}

        (_, bb_branch, _, _) = self._get_bitbake_info()

        for branch in branches:
            branchId += 1
            self.bblayers.branches[branchId] = layerindexlib.Branch(self.bblayers, None)
            self.bblayers.branches[branchId].define_data(branchId, branch, bb_branch)

        for entry in collections.split():
            layerpath = entry
            if entry in bbfile_collections:
                layerpath = bbfile_collections[entry]

            priority = int(self.data.getVar('BBFILE_PRIORITY_%s' % entry) or '0')
            layername = self.data.getVar('BBLAYERS_LAYERINDEX_NAME_%s' % entry) or os.path.basename(layerpath)
            layerversion = self.data.getVar('LAYERVERSION_%s' % entry) or ""
            layerurl = self._handle_git_remote(layerpath)

            layersubdir = ""
            layerrev = "<unknown>"
            layerbranch = "<unknown>"

            if os.path.isdir(layerpath):
                layerbasepath = self._run_command('git rev-parse --show-toplevel', layerpath, default=layerpath)
                if os.path.abspath(layerpath) != os.path.abspath(layerbasepath):
                    layersubdir = os.path.abspath(layerpath)[len(layerbasepath) + 1:]

                layerbranch = self._run_command('git rev-parse --abbrev-ref HEAD', layerpath, default="<unknown>")
                layerrev = self._run_command('git rev-parse HEAD', layerpath, default="<unknown>")

                for remotes in self._run_command('git remote -v', layerpath, default="").split("\n"):
                    remote = remotes.split("\t")[1].split(" ")[0]
                    if "(fetch)" == remotes.split("\t")[1].split(" ")[1]:
                        layerurl = self._handle_git_remote(remote)
                        break

            layerItemId += 1
            self.bblayers.layerItems[layerItemId] = layerindexlib.LayerItem(self.bblayers, None)
            self.bblayers.layerItems[layerItemId].define_data(layerItemId, layername, description=layerpath, vcs_url=layerurl)
            # The following two entries are unique to cooker layerItems,
            # This means they usually will not exist from remote indexes
            self.bblayers.layerItems[layerItemId].priority = priority
            self.bblayers.layerItems[layerItemId].localpath = layerpath

            for branchId in self.bblayers.branches:
                layerBranchId += 1
                self.bblayers.layerBranches[layerBranchId] = layerindexlib.LayerBranch(self.bblayers, None)
                self.bblayers.layerBranches[layerBranchId].define_data(layerBranchId, entry, layerversion, layerItemId, branchId,
                                               vcs_subdir=layersubdir, vcs_last_rev=layerrev, actual_branch=layerbranch)

        return self.bblayers


    def load_layerDependencies(self):
        """Augment previously loaded data by adding in layerDependency info"""
        if not self.bblayers:
            raise BBLayerLibException("load_bblayers doesn't appear to have been called first")

        layerDependencyId = 0
        self.bblayers.layerDependencies = {}
        for layerBranchId in self.bblayers.layerBranches:
            branchName = self.bblayers.layerBranches[layerBranchId].branch.name
            collection = self.bblayers.layerBranches[layerBranchId].collection

            def add_dependency(layerDependencyId, index, deps, required):
                try:
                    depDict = bb.utils.explode_dep_versions2(deps)
                except bb.utils.VersionStringException as vse:
                    bb.fatal('Error parsing LAYERDEPENDS_%s: %s' % (c, str(vse)))

                for dep, oplist in list(depDict.items()):
                    # We need to search ourselves, so use the _ version...
                    depLayerBranch = index.find_collection(dep, branches=[branchName])
                    if not depLayerBranch:
                        # Missing dependency?!
                        logger.error('Missing dependency %s (%s)' % (dep, branchName))
                        continue

                    # We assume that the oplist matches...
                    layerDependencyId += 1
                    layerDependency = layerindexlib.LayerDependency(index, None)
                    layerDependency.define_data(id=layerDependencyId,
                                    required=required, layerbranch=layerBranchId,
                                    dependency=depLayerBranch.layer_id)

                    logger.debug(1, '%s requires %s' % (layerDependency.layer.name, layerDependency.dependency.name))
                    index.add_element("layerDependencies", [layerDependency])

                return layerDependencyId

            deps = self.data.getVar("LAYERDEPENDS_%s" % collection)
            if deps:
                layerDependencyId = add_dependency(layerDependencyId, self.bblayers, deps, True)

            deps = self.data.getVar("LAYERRECOMMENDS_%s" % collection)
            if deps:
                layerDependencyId = add_dependency(layerDependencyId, self.bblayers, deps, False)

        return self.bblayers

    def load_recipes(self, tinfoil, full=False):
        """Augment the recipe information for the layers"""

        # Assume at some point we'll implement the 'bb' way as well...
        if not tinfoil:
            raise BBLayerLibException("You must pass a valid tinfoil to parse recipe information")

        if not self.bblayers:
            raise BBLayerLibException("load_bblayers doesn't appear to have been called first")

        recipeId = 0
        self.bblayers.recipes = {}

        if tinfoil:
            pkg_pn = tinfoil.cooker.recipecaches[''].pkg_pn
            (latest_versions, preferred_versions) = tinfoil.find_providers()
            allproviders = tinfoil.get_all_providers()
            skiplist = list(tinfoil.cooker.skiplist.keys())

        for fn in skiplist:
            recipe_parts = os.path.splitext(os.path.basename(fn))[0].split('_')
            p = recipe_parts[0]
            if len(recipe_parts) > 1:
                ver = (None, recipe_parts[1], None)
            else:
                ver = (None, 'unknown', None)
            allproviders[p].append((ver, fn))
            if not p in pkg_pn:
                pkg_pn[p] = 'dummy'
                preferred_versions[p] = (ver, fn)

        global_inherit = (self.data.getVar('INHERIT') or "").split()
        cls_re = re.compile('classes/')

        for pn in pkg_pn:
            for ((pe, pv, pr), fpath) in allproviders[pn]:
                realfn = bb.cache.virtualfn2realfn(fpath)

                filepath = os.path.dirname(realfn[0])
                filename = os.path.basename(realfn[0])

                # Compute inherits, excluding global
                recipe_inherits = tinfoil.cooker_data.inherits.get(realfn[0], [])
                inherits = []
                for cls in recipe_inherits:
                    if cls_re.match(cls):
                        continue
                    classname = os.path.splitext(os.path.basename(cls))[0]
                    if classname in global_inherit:
                        continue
                    inherits.append(classname)

                if not full:
                    recipe_data = self.data.createCopy()
                    recipe_data.setVar("PN", pn)
                    recipe_data.setVar("PV", pv)
                else:
                    recipe_data = tinfoil.parse_recipe_file(fpath, appends=False)

                summary = recipe_data.getVar('SUMMARY') or ''
                description = recipe_data.getVar('DESCRIPTION') or ''
                section = recipe_data.getVar('SECTION') or ''
                license = recipe_data.getVar('LICENSE') or ''
                homepage = recipe_data.getVar('HOMEPAGE') or ''
                bugtracker = recipe_data.getVar('BUGTRACKER') or ''
                provides = recipe_data.getVar('PROVIDES') or ''
                bbclassextend = recipe_data.getVar('BBCLASSEXTEND') or ''
                blacklisted = recipe_data.getVarFlag('PNBLACKLIST', pn) or ''

                layer = bb.utils.get_file_layer(realfn[0], self.data)

                depBranchId = self.bblayers.find_collection(layer)

                recipeId += 1
                recipe = layerindexlib.Recipe(self.bblayers, None)
                recipe.define_data(id=recipeId,
                                   filename=filename, filepath=filepath,
                                   pn=pn, pv=pv,
                                   summary=summary, description=description, section=section,
                                   license=license, homepage=homepage, bugtracker=bugtracker,
                                   provides=provides, bbclassextend=bbclassextend, inherits=' '.join(inherits),
                                   blacklisted=blacklisted, layerbranch=depBranchId)

                self.bblayers.add_element("recipes", [recipe])

        return self.bblayers

    def load_machines(self):
        """Augment the machine information for the layers"""
        if not self.bblayers:
            raise BBLayerLibException("load_bblayers doesn't appear to have been called first")

        machineId = 0
        self.bblayers.machines = {}

        for layerBranchId in self.bblayers.layerBranches:
            # load_bblayers uses the description to cache the actual path...
            machine_path = self.bblayers.layerBranches[layerBranchId].getDescription()
            machine_path = os.path.join(machine_path, 'conf/machine')
            if os.path.isdir(machine_path):
                for (dirpath, _, filenames) in os.walk(machine_path):
                    # Ignore subdirs...
                    if not dirpath.endswith('conf/machine'):
                        continue
                    for fname in filenames:
                        if fname.endswith('.conf'):
                            machineId += 1
                            machine = layerindexlib.Machine(self.bblayers, None)
                            machine.define_data(id=machineId, name=fname[:-5],
                                                description=fname[:-5],
                                                layerbranch=layerBranchId)

                            self.bblayers.add_element("machines", [machine])

        return self.bblayers

    def load_distros(self):
        """Augment the distro information for the layers"""
        if not self.bblayers:
            raise BBLayerLibException("load_bblayers doesn't appear to have been called first")

        distroId = 0
        self.bblayers.distros = {}

        for layerBranchId in self.bblayers.layerBranches:
            # load_bblayers uses the description to cache the actual path...
            distro_path = self.bblayers.layerBranches[layerBranchId].getDescription()
            distro_path = os.path.join(distro_path, 'conf/distro')
            if os.path.isdir(distro_path):
                for (dirpath, _, filenames) in os.walk(distro_path):
                    # Ignore subdirs...
                    if not dirpath.endswith('conf/distro'):
                        continue
                    for fname in filenames:
                        if fname.endswith('.conf'):
                            distroId += 1
                            distro = layerindexlib.distro(self.bblayers, None)
                            distro.define_data(id=distroId, name=fname[:-5],
                                                description=fname[:-5],
                                                layerbranch=layerBranchId)

                            self.bblayers.add_element("distros", [distro])

        return self.bblayers
