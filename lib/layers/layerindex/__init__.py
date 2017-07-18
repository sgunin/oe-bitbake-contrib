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

import datetime

import logging
import imp

import bb.fetch2

from collections import OrderedDict

logger = logging.getLogger('BitBake.layers.layerindex')

class LayerIndex():
    def __init__(self, d):
        if d:
            self.data = d
        else:
            import bb.data
            self.data = bb.data.init()
            # We need to use the fetcher to parse the URL
            # it requires DL_DIR to be set
            self.data.setVar('DL_DIR', os.getcwd())

        self.lindex = []

        self.plugins = []

        import bb.utils
        bb.utils.load_plugins(logger, self.plugins, os.path.dirname(__file__))
        for plugin in self.plugins:
            if hasattr(plugin, 'init'):
                plugin.init(self)

    def __add__(self, other):
        newIndex = LayerIndex(self.data)

        if self.__class__ != newIndex.__class__ or \
           other.__class__ != newIndex.__class__:
            raise TypeException("Can not add different types.")

        for lindexEnt in self.lindex:
            newIndex.lindex.append(lindexEnt)

        for lindexEnt in other.lindex:
            newIndex.lindex.append(lindexEnt)

        return newIndex

    def _get_plugin(self, type):
        for plugin in self.plugins:
            if hasattr(plugin, 'plugin_type'):
                plugintype = plugin.plugin_type()
                logger.debug(1, "Looking for IndexPlugin - %s ? %s" % (plugintype, type))
                if plugintype and plugintype == type:
                    return plugin
        return None

    loadRecipes = 1
    def load_layerindex(self, indexURIs, reload=False, load='layerDependencies recipes machines distros'):
        """Load the layerindex.

indexURIs- This may be one or more indexes (white space seperated).

reload - If reload is True, then any previously loaded indexes will be forgotten.

load - Ability to NOT load certain elements for performance.  White space seperated list
       of optional things to load.  (branches, layerItems and layerBranches is always
       loaded.)   Note: the plugins are permitted to ignore this and load everything.

The format of the indexURI:

  <url>;type=<type>;branch=<branch>;cache=<cache>;desc=<description>

  Note: the 'branch' parameter if set can select multiple branches by using
  comma, such as 'branch=master,morty,pyro'.  However, many operations only look
  at the -first- branch specified!

  The cache value may be undefined, in this case a network failure will
  result in an error, otherwise the system will look for a file of the cache
  name and load that instead.

  For example:

  http://layers.openembedded.org/layerindex/api/;type=restapi;branch=master;desc=OpenEmbedded%20Layer%20Index
  file://conf/bblayers.conf;type=internal

restapi is either a web url or a local file or a local directory with one
or more .json file in it in the restapi format

internal refers to any layers loaded as part of a project conf/bblayers.conf
"""
        if reload:
            self.lindex = []

        logger.debug(1, 'Loading: %s' % indexURIs)

        for url in indexURIs.split():
            ud = bb.fetch2.FetchData(url, self.data)

            if 'type' not in ud.parm:
                raise bb.fetch2.MissingParameterError('type', url)

            plugin = self._get_plugin(ud.parm['type'] or "restapi")

            if not plugin:
                raise NotImplementedError("%s: type %s is not available" % (url, ud.parm['type']))

            # TODO: Implement 'cache', for when the network is not available
            lindexEnt = plugin.load_index(ud, load)

            if 'CONFIG' not in lindexEnt:
                raise Exception('Internal Error: Missing configuration data in index %s' % url)

            # Mark CONFIG data as something we've added...
            lindexEnt['CONFIG']['local'] = []
            lindexEnt['CONFIG']['local'].append('CONFIG')

            if 'branches' not in lindexEnt:
                raise Exception('Internal Error: No branches defined in index %s' % url)

            # Create quick lookup layerBranches_layerId_branchId table
            if 'layerBranches' in lindexEnt:
                # Create associated quick lookup indexes
                lindexEnt['layerBranches_layerId_branchId'] = {}
                for layerBranchId in lindexEnt['layerBranches']:
                    obj = lindexEnt['layerBranches'][layerBranchId]
                    lindexEnt['layerBranches_layerId_branchId']["%s:%s" % (obj.get_layer_id(), obj.get_branch_id())] = obj
                # Mark layerBranches_layerId_branchId as something we added
                lindexEnt['CONFIG']['local'].append('layerBranches_layerId_branchId')

            # Create quick lookup layerDependencies_layerBranchId table
            if 'layerDependencies' in lindexEnt:
                # Create associated quick lookup indexes
                lindexEnt['layerDependencies_layerBranchId'] = {}
                for layerDependencyId in lindexEnt['layerDependencies']:
                    obj = lindexEnt['layerDependencies'][layerDependencyId]
                    if obj.get_layerbranch_id() not in lindexEnt['layerDependencies_layerBranchId']:
                        lindexEnt['layerDependencies_layerBranchId'][obj.get_layerbranch_id()] = [obj]
                    else:
                        lindexEnt['layerDependencies_layerBranchId'][obj.get_layerbranch_id()].append(obj)
                # Mark layerDependencies_layerBranchId as something we added
                lindexEnt['CONFIG']['local'].append('layerDependencies_layerBranchId')

            # Create quick lookup layerUrls
            if 'layerBranches' in lindexEnt:
                # Create associated quick lookup indexes
                lindexEnt['layerUrls'] = {}
                for layerBranchId in lindexEnt['layerBranches']:
                    obj = lindexEnt['layerBranches'][layerBranchId]
                    vcs_url = obj.get_layer().get_vcs_url()
                    if vcs_url not in lindexEnt['layerUrls']:
                        lindexEnt['layerUrls'][vcs_url] = [obj]
                    else:
                        # We insert this if there is no subdir, we know it's the parent
                        if not obj.get_vcs_subdir():
                            lindexEnt['layerUrls'][vcs_url].insert(0, obj)
                        else:
                            lindexEnt['layerUrls'][vcs_url].append(obj)
                # Mark layerUrls as something we added
                lindexEnt['CONFIG']['local'].append('layerUrls')

            self.lindex.append(lindexEnt)

    def store_layerindex(self, indexURI, lindex=None):
        """Store a layerindex

Typically this will be used to create a local cache file of a remote index.

  file://<path>;type=<type>;branch=<branch>

We can write out in either the restapi or django formats.  The split option
will write out the individual elements split by layer and related components.
"""
        if not lindex:
            logger.warning('No index to write, nothing to do.')
            return

        ud = bb.fetch2.FetchData(indexURI, self.data)

        if 'type' not in ud.parm:
            raise bb.fetch2.MissingParameterError('type', indexURI)

        plugin = self._get_plugin(ud.parm['type'])

        if not plugin:
            raise NotImplementedError("%s: type %s is not available" % (url, ud.parm['type']))

        lindexEnt = plugin.store_index(ud, lindex)


    def get_json_query(self, query):
        """Return a query in restapi format

This is a compatibility function.  It will acts like the web restapi query
and return back the information related to a specific query.  It can be used
but other components of the system that would rather deal with restapi
style queries then the regular functions in this class.

Note: only select queries are supported.  This will have to be expanded
to support additional queries.

This function will merge multiple databases together to return a single
coherent 'superset' result, when more then one index has been loaded.
"""

        # TODO Implement get_json_query
        raise Exception("get_json_query: not Implemented!")

    def is_empty(self):
        """Return True or False if the index has any usable data.

We check the lindex entries to see if they have a branch set, as well as
layerBranches set.  If not, they are effectively blank."""

        found = False
        for lindex in self.lindex:
            if 'branches' in lindex and 'layerBranches' in lindex and \
               lindex['branches'] and lindex['layerBranches']:
                found = True
                break
        return not found


    def find_vcs_url(self, vcs_url, branch=None):
        """Return the first layerBranch with the given vcs_url

If a branch has not been specified, we will iterate over the branches in
the default configuration until the first vcs_url/branch match."""

        for lindex in self.lindex:
            logger.debug(1, ' searching %s' % lindex['CONFIG']['DESCRIPTION'])
            layerBranch = self._find_vcs_url(lindex, vcs_url, branch)
            if layerBranch:
                return layerBranch
        return None

    def _find_vcs_url(self, lindex, vcs_url, branch=None):
        if 'branches' not in lindex or 'layerBranches' not in lindex:
            return None

        if vcs_url in lindex['layerUrls']:
            for layerBranch in lindex['layerUrls'][vcs_url]:
                if branch and branch == layerBranch.get_branch().get_name():
                    return layerBranch
                if not branch:
                    return layerBranch

        return None


    def find_collection(self, collection, version=None, branch=None):
        """Return the first layerBranch with the given collection name

If a branch has not been specified, we will iterate over the branches in
the default configuration until the first colelction/branch match."""

        logger.debug(1, 'find_collection: %s (%s) %s' % (collection, version, branch))

        for lindex in self.lindex:
            logger.debug(1, ' searching %s' % lindex['CONFIG']['DESCRIPTION'])
            layerBranch = self._find_collection(lindex, collection, version, branch)
            if layerBranch:
                return layerBranch
        else:
            logger.debug(1, 'Collection %s (%s) not found for branch (%s)' % (collection, version, branch))
        return None

    def _find_collection(self, lindex, collection, version=None, branch=None):
        if 'branches' not in lindex or 'layerBranches' not in lindex:
            return None

        def find_branch_layerItem(branch, collection, version):
            for branchId in lindex['branches']:
                if branch == lindex['branches'][branchId].get_name():
                    break
            else:
                return None

            for layerBranchId in lindex['layerBranches']:
                if branchId == lindex['layerBranches'][layerBranchId].get_branch_id() and \
                   collection == lindex['layerBranches'][layerBranchId].get_collection():
                    if not version or version == lindex['layerBranches'][layerBranchId].get_version():
                        return lindex['layerBranches'][layerBranchId]

            return None

        if branch:
            layerBranch = find_branch_layerItem(branch, collection, version)
            return layerBranch

        # No branch, so we have to scan the branches in order...
        # Use the config order if we have it...
        if 'CONFIG' in lindex and 'BRANCH' in lindex['CONFIG']:
            for branch in lindex['CONFIG']['BRANCH'].split(','):
                layerBranch = find_branch_layerItem(branch, collection, version)
                if layerBranch:
                    return layerBranch

        # ...use the index order if we don't...
        else:
            for branchId in lindex['branches']:
                branch = lindex['branches'][branchId].get_name()
                layerBranch = get_branch_layerItem(branch, collection, version)
                if layerBranch:
                    return layerBranch

        return None


    def get_layerbranch(self, name, branch=None):
        """Return the layerBranch item for a given name and branch

If a branch has not been specified, we will iterate over the branches in
the default configuration until the first name/branch match."""

        for lindex in self.lindex:
            layerBranch = self._get_layerbranch(lindex, name, branch)
            if layerBranch:
                return layerBranch
        return None

    def _get_layerbranch(self, lindex, name, branch=None):
        if 'branches' not in lindex or 'layerItems' not in lindex:
            logger.debug(1, 'No branches or no layerItems in lindex %s' % (lindex['CONFIG']['DESCRIPTION']))
            return None

        def get_branch_layerItem(branch, name):
            for branchId in lindex['branches']:
                if branch == lindex['branches'][branchId].get_name():
                    break
            else:
                return None

            for layerItemId in lindex['layerItems']:
                if name == lindex['layerItems'][layerItemId].get_name():
                    break
            else:
                return None

            key = "%s:%s" % (layerItemId, branchId)
            if key in lindex['layerBranches_layerId_branchId']:
                return lindex['layerBranches_layerId_branchId'][key]
            return None

        if branch:
            layerBranch = get_branch_layerItem(branch, name)
            return layerBranch

        # No branch, so we have to scan the branches in order...
        # Use the config order if we have it...
        if 'CONFIG' in lindex and 'BRANCH' in lindex['CONFIG']:
            for branch in lindex['CONFIG']['BRANCH'].split(','):
                layerBranch = get_branch_layerItem(branch, name)
                if layerBranch:
                    return layerBranch

        # ...use the index order if we don't...
        else:
            for branchId in lindex['branches']:
                branch = lindex['branches'][branchId].get_name()
                layerBranch = get_branch_layerItem(branch, name)
                if layerBranch:
                    return layerBranch
        return None

    def get_dependencies(self, names=None, layerBranches=None, ignores=None):
        """Return a tuple of all dependencies and invalid items.

The dependency scanning happens with a depth-first approach, so the returned
dependencies should be in the best order to define a bblayers.

names - a space deliminated list of layerItem names.
Branches are resolved in the order of the specified index's load.  Subsequent
branch resolution is on the same branch.

layerBranches - a list of layerBranches to resolve dependencies
Branches are the same as the passed in layerBranch.

ignores - a list of layer names to ignore

Return value: (dependencies, invalid)

dependencies is an orderedDict, with the key being the layer name.
The value is a list with the first ([0]) being the layerBranch, and subsequent
items being the layerDependency entries that caused this to be added.

invalid is just a list of dependencies that were not found.
"""
        invalid = []

        if not layerBranches:
            layerBranches = []

        if names:
            for name in names.split():
                if ignores and name in ignores:
                    continue

                # Since we don't have a branch, we have to just find the first
                # layerBranch with that name...
                for lindex in self.lindex:
                    layerBranch = self._get_layerbranch(lindex, name)
                    if not layerBranch:
                        # Not in this index, hopefully it's in another...
                        continue

                    if layerBranch not in layerBranches:
                        layerBranches.append(layerBranch)
                    break
                else:
                    logger.warning("Layer %s not found.  Marked as invalid." % name)
                    invalid.append(name)
                    layerBranch = None

        # Format is required['name'] = [ layer_branch, dependency1, dependency2, ..., dependencyN ]
        dependencies = OrderedDict()
        (dependencies, invalid) = self._get_dependencies(layerBranches, ignores, dependencies, invalid)

        for layerBranch in layerBranches:
            if layerBranch.get_layer().get_name() not in dependencies:
                dependencies[layerBranch.get_layer().get_name()] = [layerBranch]

        return (dependencies, invalid)


    def _get_dependencies(self, layerBranches, ignores, dependencies, invalid):
        for layerBranch in layerBranches:
            name = layerBranch.get_layer().get_name()
            # Do we ignore it?
            if ignores and name in ignores:
                continue

            if 'layerDependencies_layerBranchId' not in layerBranch.index:
                raise Exception('Missing layerDepedencies_layerBranchId cache! %s' % layerBranch.index['CONFIG']['DESCRIPTION'])

            # Get a list of dependencies and then recursively process them
            if layerBranch.get_id() in layerBranch.index['layerDependencies_layerBranchId']:
                for layerDependency in layerBranch.index['layerDependencies_layerBranchId'][layerBranch.get_id()]:
                    depLayerBranch = layerDependency.get_dependency_layerBranch()

                    # Do we need to resolve across indexes?
                    if depLayerBranch.index != self.lindex[0]:
                        rdepLayerBranch = self.find_collection(
                                          collection=depLayerBranch.get_collection(),
                                          version=depLayerBranch.get_version()
                                     )
                        if rdepLayerBranch != depLayerBranch:
                            logger.debug(1, 'Replaced %s:%s:%s with %s:%s:%s' % \
                                  (depLayerBranch.index['CONFIG']['DESCRIPTION'],
                                   depLayerBranch.get_branch().get_name(),
                                   depLayerBranch.get_layer().get_name(),
                                   rdepLayerBranch.index['CONFIG']['DESCRIPTION'],
                                   rdepLayerBranch.get_branch().get_name(),
                                   rdepLayerBranch.get_layer().get_name()))
                            depLayerBranch = rdepLayerBranch

                    # Is this dependency on the list to be ignored?
                    if ignores and depLayerBranch.get_layer().get_name() in ignores:
                        continue

                    # Previously found dependencies have been processed, as
                    # have their dependencies...
                    if depLayerBranch.get_layer().get_name() not in dependencies:
                        (dependencies, invalid) = self._get_dependencies([depLayerBranch], ignores, dependencies, invalid)

                    if depLayerBranch.get_layer().get_name() not in dependencies:
                        dependencies[depLayerBranch.get_layer().get_name()] = [depLayerBranch, layerDependency]
                    else:
                        if layerDependency not in dependencies[depLayerBranch.get_layer().get_name()]:
                            dependencies[depLayerBranch.get_layer().get_name()].append(layerDependency)

        return (dependencies, invalid)


    def list_obj(self, object):
        """Print via the plain logger object information

This function is used to implement debugging and provide the user info.
"""
        for lix in self.lindex:
            if object not in lix:
                continue

            logger.plain ('')
            logger.plain('Index: %s' % lix['CONFIG']['DESCRIPTION'])

            output = []

            if object == 'branches':
                logger.plain ('%s %s %s' % ('{:26}'.format('branch'), '{:34}'.format('description'), '{:22}'.format('bitbake branch')))
                logger.plain ('{:-^80}'.format(""))
                for branchId in lix['branches']:
                    output.append('%s %s %s' % (
                                  '{:26}'.format(lix['branches'][branchId].get_name()),
                                  '{:34}'.format(lix['branches'][branchId].get_short_description()),
                                  '{:22}'.format(lix['branches'][branchId].get_bitbake_branch())
                                 ))
                for line in sorted(output):
                    logger.plain (line)

                continue

            if object == 'layerItems':
                logger.plain ('%s %s' % ('{:26}'.format('layer'), '{:34}'.format('description')))
                logger.plain ('{:-^80}'.format(""))
                for layerId in lix['layerItems']:
                    output.append('%s %s' % (
                                  '{:26}'.format(lix['layerItems'][layerId].get_name()),
                                  '{:34}'.format(lix['layerItems'][layerId].get_summary())
                                 ))
                for line in sorted(output):
                    logger.plain (line)

                continue

            if object == 'layerBranches':
                logger.plain ('%s %s %s' % ('{:26}'.format('layer'), '{:34}'.format('description'), '{:19}'.format('collection:version')))
                logger.plain ('{:-^80}'.format(""))
                for layerBranchId in lix['layerBranches']:
                    output.append('%s %s %s' % (
                                  '{:26}'.format(lix['layerBranches'][layerBranchId].get_layer().get_name()),
                                  '{:34}'.format(lix['layerBranches'][layerBranchId].get_layer().get_summary()),
                                  '{:19}'.format("%s:%s" %
                                                          (lix['layerBranches'][layerBranchId].get_collection(),
                                                           lix['layerBranches'][layerBranchId].get_version())
                                                )
                                 ))
                for line in sorted(output):
                    logger.plain (line)

                continue

            if object == 'layerDependencies':
                logger.plain ('%s %s %s %s' % ('{:19}'.format('branch'), '{:26}'.format('layer'), '{:11}'.format('dependency'), '{:26}'.format('layer')))
                logger.plain ('{:-^80}'.format(""))
                for layerDependency in lix['layerDependencies']:
                    if not lix['layerDependencies'][layerDependency].get_dependency_layerBranch():
                        continue

                    output.append('%s %s %s %s' % (
                                  '{:19}'.format(lix['layerDependencies'][layerDependency].get_layerbranch().get_branch().get_name()),
                                  '{:26}'.format(lix['layerDependencies'][layerDependency].get_layerbranch().get_layer().get_name()),
                                  '{:11}'.format('requires' if lix['layerDependencies'][layerDependency].is_required() else 'recommends'),
                                  '{:26}'.format(lix['layerDependencies'][layerDependency].get_dependency_layerBranch().get_layer().get_name())
                                 ))
                for line in sorted(output):
                    logger.plain (line)

                continue

            if object == 'recipes':
                logger.plain ('%s %s %s' % ('{:20}'.format('recipe'), '{:10}'.format('version'), 'layer'))
                logger.plain ('{:-^80}'.format(""))
                output = []
                for recipe in lix['recipes']:
                    output.append('%s %s %s' % (
                                  '{:30}'.format(lix['recipes'][recipe].get_pn()),
                                  '{:30}'.format(lix['recipes'][recipe].get_pv()),
                                  lix['recipes'][recipe].get_layer().get_name()
                                 ))
                for line in sorted(output):
                    logger.plain (line)

                continue

            if object == 'machines':
                logger.plain ('%s %s %s' % ('{:24}'.format('machine'), '{:34}'.format('description'), '{:19}'.format('layer')))
                logger.plain ('{:-^80}'.format(""))
                for machine in lix['machines']:
                    output.append('%s %s %s' % (
                                  '{:24}'.format(lix['machines'][machine].get_name()),
                                  ('{:34}'.format(lix['machines'][machine].get_description()))[:34],
                                  '{:19}'.format(lix['machines'][machine].get_layerbranch().get_layer().get_name() )
                                 ))
                for line in sorted(output):
                    logger.plain (line)

                continue

            if object == 'distros':
                logger.plain ('%s %s %s' % ('{:24}'.format('distro'), '{:34}'.format('description'), '{:19}'.format('layer')))
                logger.plain ('{:-^80}'.format(""))
                for distro in lix['distros']:
                    output.append('%s %s %s' % (
                                  '{:24}'.format(lix['distros'][distro].get_name()),
                                  ('{:34}'.format(lix['distros'][distro].get_description()))[:34],
                                  '{:19}'.format(lix['distros'][distro].get_layerbranch().get_layer().get_name() )
                                 ))
                for line in sorted(output):
                    logger.plain (line)

                continue

        logger.plain ('')

# Define enough of the layer index types so we can easily resolve them...
# It is up to the loaders to create the classes from the raw data
class LayerIndexItem():
    def __init__(self, index, data):
        self.index = index
        self.data = data

    def __eq__(self, other):
        if self.__class__ != other.__class__:
            return False
        res=(self.data == other.data)
        logger.debug(2, 'Compare objects: %s ? %s : %s' % (self.get_id(), other.get_id(), res))
        return res

    def define_data(self, id):
        self.data = {}
        self.data['id'] = id

    def get_id(self):
        return self.data['id']


class Branch(LayerIndexItem):
    def define_data(self, id, name, bitbake_branch,
                 short_description=None, sort_priority=1,
                 updates_enabled=True, updated=None,
                 update_environment=None):
        self.data = {}
        self.data['id'] = id
        self.data['name'] = name
        self.data['bitbake_branch'] = bitbake_branch
        self.data['short_description'] = short_description or name
        self.data['sort_priority'] = sort_priority
        self.data['updates_enabled'] = updates_enabled
        self.data['updated'] = updated or datetime.datetime.today().isoformat()
        self.data['update_environment'] = update_environment

    def get_name(self):
        return self.data['name']

    def get_short_description(self):
        return self.data['short_description'].strip()

    def get_bitbake_branch(self):
        return self.data['bitbake_branch'] or self.get_name()


class LayerItem(LayerIndexItem):
    def define_data(self, id, name, status='P',
                 layer_type='A', summary=None,
                 description=None,
                 vcs_url=None, vcs_web_url=None,
                 vcs_web_tree_base_url=None,
                 vcs_web_file_base_url=None,
                 usage_url=None,
                 mailing_list_url=None,
                 index_preference=1,
                 classic=False,
                 updated=None):
        self.data = {}
        self.data['id'] = id
        self.data['name'] = name
        self.data['status'] = status
        self.data['layer_type'] = layer_type
        self.data['summary'] = summary or name
        self.data['description'] = description or summary or name
        self.data['vcs_url'] = vcs_url
        self.data['vcs_web_url'] = vcs_web_url
        self.data['vcs_web_tree_base_url'] = vcs_web_tree_base_url
        self.data['vcs_web_file_base_url'] = vcs_web_file_base_url
        self.data['index_preference'] = index_preference
        self.data['classic'] = classic
        self.data['updated'] = updated or datetime.datetime.today().isoformat()

    def get_name(self):
        return self.data['name']

    def get_summary(self):
        return self.data['summary']

    def get_description(self):
        return self.data['description'].strip()

    def get_vcs_url(self):
        return self.data['vcs_url']

    def get_vcs_web_url(self):
        return self.data['vcs_web_url']

    def get_vcs_web_tree_base_url(self):
        return self.data['vcs_web_tree_base_url']

    def get_vcs_web_file_base_url(self):
        return self.data['vcs_web_file_base_url']

    def get_updated(self):
        return self.data['updated']

class LayerBranch(LayerIndexItem):
    def define_data(self, id, collection, version, layer, branch,
                 vcs_subdir="", vcs_last_fetch=None,
                 vcs_last_rev=None, vcs_last_commit=None,
                 actual_branch="",
                 updated=None):
        self.data = {}
        self.data['id'] = id
        self.data['collection'] = collection
        self.data['version'] = version
        self.data['layer'] = layer
        self.data['branch'] = branch
        self.data['vcs_subdir'] = vcs_subdir
        self.data['vcs_last_fetch'] = vcs_last_fetch
        self.data['vcs_last_rev'] = vcs_last_rev
        self.data['vcs_last_commit'] = vcs_last_commit
        self.data['actual_branch'] = actual_branch
        self.data['updated'] = updated or datetime.datetime.today().isoformat()

    def get_collection(self):
        return self.data['collection']

    def get_version(self):
        return self.data['version']

    def get_vcs_subdir(self):
        return self.data['vcs_subdir']

    def get_actual_branch(self):
        return self.data['actual_branch'] or self.get_branch().get_name()

    def get_updated(self):
        return self.data['updated']

    def get_layer_id(self):
        return self.data['layer']

    def get_branch_id(self):
        return self.data['branch']

    def get_layer(self):
        layerItem = None
        try:
            layerItem = self.index['layerItems'][self.get_layer_id()]
        except KeyError:
            logger.error('Unable to find layerItems in index')
        except IndexError:
            logger.error('Unable to find layerId %s' % self.get_layer_id())
        return layerItem

    def get_branch(self):
        branch = None
        try:
            branch = self.index['branches'][self.get_branch_id()]
        except KeyError:
            logger.error('Unable to find branches in index: %s' % self.index.keys())
        except IndexError:
            logger.error('Unable to find branchId %s' % self.get_branch_id())
        return branch


class LayerIndexItem_LayerBranch(LayerIndexItem):
    def get_layerbranch_id(self):
        return self.data['layerbranch']

    def get_layerbranch(self):
        layerBranch = None
        try:
            layerBranch = self.index['layerBranches'][self.get_layerbranch_id()]
        except KeyError:
            logger.error('Unable to find layerBranches in index')
        except IndexError:
            logger.error('Unable to find layerBranchId %s' % self.get_layerbranch_id())
        return layerBranch

    def get_layer_id(self):
        layerBranch = self.get_layerbranch()
        if layerBranch:
            return layerBranch.get_layer_id()
        return None

    def get_layer(self):
        layerBranch = self.get_layerbranch()
        if layerBranch:
            return layerBranch.get_layer()
        return None

class LayerDependency(LayerIndexItem_LayerBranch):
    def define_data(self, id, layerbranch, dependency, required=True):
        self.data = {}
        self.data['id'] = id
        self.data['layerbranch'] = layerbranch
        self.data['dependency'] = dependency
        self.data['required'] = required

    def is_required(self):
        return self.data['required']

    def get_dependency_id(self):
        return self.data['dependency']

    def get_dependency_layer(self):
        layerItem = None
        try:
            layerItem = self.index['layerItems'][self.get_dependency_id()]
        except KeyError:
            logger.error('Unable to find layerItems in index')
        except IndexError:
            logger.error('Unable to find layerId %s' % self.get_dependency_id())
        return layerItem

    def get_dependency_layerBranch(self):
        layerBranch = None
        try:
            layerId = self.get_dependency_id()
            branchId = self.get_layerbranch().get_branch_id()
            layerBranch = self.index['layerBranches_layerId_branchId']["%s:%s" % (layerId, branchId)]
        except KeyError:
            logger.warning('Unable to find layerBranches_layerId_branchId in index')

            # We don't have a quick lookup index, doing it the slower way...
            layerId = self.get_dependency_id()
            branchId = self.get_layerbranch().get_branch_id()
            for layerBranchId in self.index['layerBranches']:
                layerBranch = self.index['layerBranches'][layerBranchId]
                if layerBranch.get_layer_id() == layerId and \
                   layerBranch.get_branch_id() == branchId:
                    break
            else:
                logger.error("LayerBranch not found layerId %s -- BranchId %s" % (layerId, branchId))
                layerBranch = None
        except IndexError:
            logger.error("LayerBranch not found layerId %s -- BranchId %s" % (layerId, branchId))

        return layerBranch


class Recipe(LayerIndexItem_LayerBranch):
    def define_data(self, id,
                    filename, filepath, pn, pv, layerbranch,
                    summary="", description="", section="", license="",
                    homepage="", bugtracker="", provides="", bbclassextend="",
                    inherits="", blacklisted="", updated=None):
        self.data = {}
        self.data['id'] = id
        self.data['filename'] = filename
        self.data['filepath'] = filepath
        self.data['pn'] = pn
        self.data['pv'] = pv
        self.data['summary'] = summary
        self.data['description'] = description
        self.data['section'] = section
        self.data['license'] = license
        self.data['homepage'] = homepage
        self.data['bugtracker'] = bugtracker
        self.data['provides'] = provides
        self.data['bbclassextend'] = bbclassextend
        self.data['inherits'] = inherits
        self.data['updated'] = updated or datetime.datetime.today().isoformat()
        self.data['blacklisted'] = blacklisted
        self.data['layerbranch'] = layerbranch

    def get_filename(self):
        return self.data['filename']

    def get_filepath(self):
        return self.data['filepath']

    def get_fullpath(self):
        return os.path.join(self.data['filepath'], self.data['filename'])

    def get_summary(self):
        return self.data['summary']

    def get_description(self):
        return self.data['description'].strip()

    def get_section(self):
        return self.data['section']

    def get_pn(self):
        return self.data['pn']

    def get_pv(self):
        return self.data['pv']

    def get_license(self):
        return self.data['license']

    def get_homepage(self):
        return self.data['homepage']

    def get_bugtracker(self):
        return self.data['bugtracker']

    def get_provides(self):
        return self.data['provides']

    def get_updated(self):
        return self.data['updated']

    def get_inherits(self):
        if 'inherits' not in self.data:
            # Older indexes may not have this, so emulate it
            if '-image-' in self.get_pn():
                return 'image'
        return self.data['inherits']


class Machine(LayerIndexItem_LayerBranch):
    def define_data(self, id,
                    name, description, layerbranch,
                    updated=None):
        self.data = {}
        self.data['id'] = id
        self.data['name'] = name
        self.data['description'] = description
        self.data['layerbranch'] = layerbranch
        self.data['updated'] = updated or datetime.datetime.today().isoformat()

    def get_name(self):
        return self.data['name']

    def get_description(self):
        return self.data['description'].strip()

    def get_updated(self):
        return self.data['updated']

class Distro(LayerIndexItem_LayerBranch):
    def define_data(self, id,
                    name, description, layerbranch,
                    updated=None):
        self.data = {}
        self.data['id'] = id
        self.data['name'] = name
        self.data['description'] = description
        self.data['layerbranch'] = layerbranch
        self.data['updated'] = updated or datetime.datetime.today().isoformat()

    def get_name(self):
        return self.data['name']

    def get_description(self):
        return self.data['description'].strip()

    def get_updated(self):
        return self.data['updated']

# When performing certain actions, we may need to sort the data.
# This will allow us to keep it consistent from run to run.
def sort_entry(item):
    newitem = item
    try:
        if type(newitem) == type(dict()):
            newitem = OrderedDict(sorted(newitem.items(), key=lambda t: t[0]))
            for index in newitem:
                newitem[index] = sort_entry(newitem[index])
        elif type(newitem) == type(list()):
            newitem.sort(key=lambda obj: obj['id'])
            for index, _ in enumerate(newitem):
                newitem[index] = sort_entry(newitem[index])
    except:
        logger.error('Sort failed for item %s' % type(item))
        pass

    return newitem
