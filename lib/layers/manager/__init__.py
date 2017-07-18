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

import logging

import layers.layerindex

import tempfile

import shutil

logger = logging.getLogger('BitBake.layers.manager')

class LayerManager():
    def __init__(self, d, cooker):
        _set_manager(self)

        self.data = d
        # Cooker isn't currently used by this module, but may be referenced
        # by other layer modules or plugins.  This is a single convienent
        # place to define it.
        self.cooker = cooker

        self.local_index = None  # What is in the bblayers.conf
        self.layers = None       # The layers we want to setup (get_dependency format)
        self.ignore = None       # Specific items to ignore on fetch/unpack

        self.plugins = []
        bb.utils.load_plugins(logger, self.plugins, os.path.dirname(__file__))
        for plugin in self.plugins:
            if hasattr(plugin, 'init'):
                plugin.init(self)

    def get_plugin(self, type):
        for plugin in self.plugins:
            if hasattr(plugin, 'plugin_type'):
                plugintype = plugin.plugin_type()
                logger.debug(1, "Looking for LayerManagerPlugin - %s ? %s" % (plugintype, type))
                if plugintype and plugintype == type:
                    return plugin
        return None

    def _run_command(self, command, path, default=None):
        try:
            result, _ = bb.process.run(command, cwd=path)
            result = result.strip()
        except bb.process.ExecutionError:
            result = default
        return result

    def get_bitbake_info(self):
        """Return a tuple of bitbake information"""

        # Our path SHOULD be .../bitbake/lib/layers/manager/__init__.py
        bb_path = os.path.dirname(__file__) # .../bitbake/lib/layers/manager/__init__.py
        bb_path = os.path.dirname(bb_path)  # .../bitbake/lib/layers/manager
        bb_path = os.path.dirname(bb_path)  # .../bitbake/lib/layers
        bb_path = os.path.dirname(bb_path)  # .../bitbake/lib
        bb_path = os.path.dirname(bb_path)  # .../bitbake
        bb_path = self._run_command('git rev-parse --show-toplevel', os.path.dirname(__file__), default=bb_path)
        bb_branch = self._run_command('git rev-parse --abbrev-ref HEAD', bb_path, default="<unknown>")
        bb_rev = self._run_command('git rev-parse HEAD', bb_path, default="<unknown>")
        for remotes in self._run_command('git remote -v', bb_path, default="").split("\n"):
            remote = remotes.split("\t")[1].split(" ")[0]
            if "(fetch)" == remotes.split("\t")[1].split(" ")[1]:
                bb_remote = _handle_git_remote(remote)
                break
        else:
            bb_remote = _handle_git_remote(bb_path)

        return (bb_remote, bb_branch, bb_rev, bb_path)

    def load_bblayers(self, d=None):
        """Load the BBLAYERS and related collection information"""
        if d is None:
            d = self.data

        default_branches = d.getVar('LAYERSERIES_CORENAMES') or "HEAD"

        index = {}

        branchId = 0
        index['branches'] = {}

        layerItemId = 0
        index['layerItems'] = {}

        layerBranchId = 0
        index['layerBranches'] = {}

        bblayers = d.getVar('BBLAYERS').split()

        if not bblayers:
            # It's blank!  Nothing to process...
            return index

        collections = d.getVar('BBFILE_COLLECTIONS')
        layerconfs = d.varhistory.get_variable_items_files('BBFILE_COLLECTIONS', d)
        bbfile_collections = {layer: os.path.dirname(os.path.dirname(path)) for layer, path in layerconfs.items()}

        (_, bb_branch, _, _) = self.get_bitbake_info()

        for branch in default_branches.split():
            branchId += 1
            index['branches'][branchId] = layers.layerindex.Branch(index, None)
            index['branches'][branchId].define_data(branchId, branch, bb_branch)

        for entry in collections.split():
            layerpath = entry
            if entry in bbfile_collections:
                layerpath = bbfile_collections[entry]

            layername = d.getVar('BBLAYERS_LAYERINDEX_NAME_%s' % entry) or os.path.basename(layerpath)
            layerversion = d.getVar('LAYERVERSION_%s' % entry) or ""
            layerurl = _handle_git_remote(layerpath)

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
                        layerurl = _handle_git_remote(remote)
                        break

            layerItemId += 1
            index['layerItems'][layerItemId] = layers.layerindex.LayerItem(index, None)
            index['layerItems'][layerItemId].define_data(layerItemId, layername, description=layerpath, vcs_url=layerurl)

            for branchId in index['branches']:
                layerBranchId += 1
                index['layerBranches'][layerBranchId] = layers.layerindex.LayerBranch(index, None)
                index['layerBranches'][layerBranchId].define_data(layerBranchId, entry, layerversion, layerItemId, branchId,
                                               vcs_subdir=layersubdir, vcs_last_rev=layerrev, actual_branch=layerbranch)

        return index

    def get_clone_base_directory(self):
        return self.data.getVar('BBLAYERS_FETCH_DIR')

    # You are not allowed to have two of the same url, but different branches
    def get_clone_directory(self, url):
        baseDir = self.get_clone_base_directory()
        if not baseDir:
            return None
        repo = os.path.basename(url)
        return os.path.join(baseDir, repo)

    def setup(self, layers, ignore=None):
        """Setup the data structures for fetch and unpack and update bblayers.conf

layers - format returned by LayerIndex.getDependencies
ignore - a text string with a space deliminated list of layerItem names to ignore when downloading."""

        self.local_index = self.load_bblayers()
        self.layers = layers
        self.ignore = (ignore or "").split()

        self.index_fetcher = self.data.getVar('BBLAYERS_FETCHER_TYPE') or 'fetcher'

        plugin = self.get_plugin(self.index_fetcher)
        if not plugin:
            raise NotImplementedError("layer manager plugin %s is not available" % index_fetcher)

        plugin.setup()


    def fetch(self):
        """Fetch the layers from setup"""

        plugin = self.get_plugin(self.index_fetcher)
        if not plugin:
            raise NotImplementedError("layer manager plugin %s is not available" % index_fetcher)

        plugin.fetch()


    def unpack(self):
        """unpack the layers from fetch"""

        plugin = self.get_plugin(self.index_fetcher)
        if not plugin:
            raise NotImplementedError("layer manager plugin %s is not available" % index_fetcher)

        plugin.unpack()


    def update_bblayers(self):
        """Update the bblayers.conf file"""

        plugin = self.get_plugin(self.index_fetcher)
        if not plugin:
            raise NotImplementedError("layer manager plugin %s is not available" % index_fetcher)

        layerdirs = plugin.get_new_layers()

        topdir = self.data.getVar('TOPDIR')
        bblayers_conf = os.path.join(topdir, 'conf', 'bblayers.conf')
        if not os.path.exists(bblayers_conf):
            raise Exception('Unable to find bblayers.conf: %s' % bblayers_conf)

        # Back up bblayers.conf to tempdir before we add layers
        tempdir = tempfile.mkdtemp()
        backup = tempdir + "/bblayers.conf.bak"
        shutil.copy2(bblayers_conf, backup)

        try:
            notadded, _ = bb.utils.edit_bblayers_conf(bblayers_conf, layerdirs, None)
        except Exception as e:
            shutil.copy2(backup, bblayers_conf)
            raise e
        finally:
            # Remove the back up copy of bblayers.conf
            shutil.rmtree(tempdir)

def _set_manager(manager):
    global _manager
    _manager = manager

def _get_manager():
    global _manager
    return _manager

def _handle_git_remote(remote):
    if "://" not in remote:
        if ':' in remote:
            # This is assumed to be ssh
            remote = "ssh://" + remote
        else:
            # This is assumed to be a file path
            remote = "file://" + remote
    return remote
