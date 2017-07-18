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
import bb.fetch2
import json
from urllib.parse import unquote

import layers.layerindex

from layers.layerindex.common import IndexPlugin
from layers.layerindex.common import fetch_url
from layers.layerindex.common import LayerIndexError
from layers.layerindex.common import add_raw_element

logger = logging.getLogger('BitBake.layers.layerindex.restapi')

def plugin_init(plugins):
    return RestApiPlugin()

class RestApiPlugin(IndexPlugin):
    def __init__(self):
        self.type = "restapi"

    def load_index(self, ud, load):
        """
            Fetches layer information from a local or remote layer index.

            The return value is a dictionary containing API,
            layer, branch, dependency, recipe, machine, distro, information.

            url is the url to the rest api of the layer index, such as:
            http://layers.openembedded.org/layerindex/api/

            Or a local file...
        """

        if ud.type == 'file':
            return self.load_index_file(ud, load)

        if ud.type == 'http' or ud.type == 'https':
            return self.load_index_web(ud, load)

        raise bb.fetch2.FetchError('%s is not a supported protocol, only file, http and https are support.')


    def load_index_file(self, ud, load):
        """
            Fetches layer information from a local file or directory.
            The return value is a dictionary containing API,
            layer, branch, dependency, recipe, machine, distro,
            and template information.

            ud is the parsed url to the local file or directory.
        """
        if not os.path.exists(ud.path):
            raise FileNotFoundError(ud.path)

        lindex = {}

        lindex['CONFIG'] = {}
        lindex['CONFIG']['TYPE'] = self.type
        lindex['CONFIG']['URL'] = ud.url

        if 'desc' in ud.parm:
            lindex['CONFIG']['DESCRIPTION'] = unquote(ud.parm['desc'])
        else:
            lindex['CONFIG']['DESCRIPTION'] = ud.path

        if 'cache' in ud.parm:
            lindex['CONFIG']['CACHE'] = ud.parm['cache']

        branches = None
        if 'branch' in ud.parm:
            branches = ud.parm['branch']
            lindex['CONFIG']['BRANCH'] = branches


        def load_cache(path, lindex, branches=None):
            logger.debug(1, 'Loading json file %s' % path)
            pindex = json.load(open(path, 'rt', encoding='utf-8'))

            # Filter the branches on loaded files...
            newpBranch = []
            if branches:
                for branch in (branches or "").split('OR'):
                    if 'branches' in pindex:
                        for br in pindex['branches']:
                            if br['name'] == branch:
                                newpBranch.append(br)
            else:
                if 'branches' in pindex:
                    newpBranch = pindex['branches']

            if newpBranch:
                lindex = add_raw_element('branches', layers.layerindex.Branch, { 'branches' : newpBranch }, lindex)
            else:
                logger.debug(1, 'No matching branchs (%s) in index file(s)' % branches)
                # No matching branches.. return nothing...
                return

            for (lName, lType) in [("layerItems", layers.layerindex.LayerItem),
                                   ("layerBranches", layers.layerindex.LayerBranch),
                                   ("layerDependencies", layers.layerindex.LayerDependency),
                                   ("recipes", layers.layerindex.Recipe),
                                   ("machines", layers.layerindex.Machine),
                                   ("distros", layers.layerindex.Distro)]:
                if lName in pindex:
                    lindex = add_raw_element(lName, lType, pindex, lindex)


        if not os.path.isdir(ud.path):
            load_cache(ud.path, lindex, branches)
            return lindex

        logger.debug(1, 'Loading from dir %s...' % (ud.path))
        for (dirpath, _, filenames) in os.walk(ud.path):
            for filename in filenames:
                if not filename.endswith('.json'):
                    continue
                fpath = os.path.join(dirpath, filename)
                load_cache(fpath, lindex, branches)

        return lindex


    def load_index_web(self, ud, load):
        """
            Fetches layer information from a remote layer index.
            The return value is a dictionary containing API,
            layer, branch, dependency, recipe, machine, distro,
            and template information.

            ud is the parsed url to the rest api of the layer index, such as:
            http://layers.openembedded.org/layerindex/api/
        """

        def _get_json_response(apiurl=None, username=None, password=None, retry=True):
            assert apiurl is not None

            logger.debug(1, "fetching %s" % apiurl)

            res = fetch_url(apiurl, username=username, password=password)

            try:
                parsed = json.loads(res.read().decode('utf-8'))
            except ConnectionResetError:
                if retry:
                    logger.debug(1, "%s: Connection reset by peer.  Retrying..." % url)
                    parsed = _get_json_response(apiurl=apiurl, username=username, password=password, retry=False)
                    logger.debug(1, "%s: retry successful.")
                else:
                    raise bb.fetch2.FetchError('%s: Connection reset by peer.  Is there a firewall blocking your connection?' % apiurl)

            return parsed

        lindex = {}

        lindex['CONFIG'] = {}
        lindex['CONFIG']['TYPE'] = self.type
        lindex['CONFIG']['URL'] = ud.url

        if 'desc' in ud.parm:
            lindex['CONFIG']['DESCRIPTION'] = unquote(ud.parm['desc'])
        else:
            lindex['CONFIG']['DESCRIPTION'] = ud.host

        if 'cache' in ud.parm:
            lindex['CONFIG']['CACHE'] = ud.parm['cache']

        if 'branch' in ud.parm:
            lindex['CONFIG']['BRANCH'] = ud.parm['branch']

        try:
            lindex['apilinks'] = _get_json_response(bb.fetch2.encodeurl( (ud.type, ud.host, ud.path, None, None, None) ),
                                                    username=ud.user, password=ud.pswd)
        except Exception as e:
            raise LayerIndexError("Unable to load layer index %s: %s" % (ud.url, e))

        branches = None
        if 'branch' in ud.parm and ud.parm['branch']:
            branches = ud.parm['branch']


        # Local raw index set...
        pindex = {}

        # Load the branches element
        filter = ""
        if branches:
            filter = "?filter=name:%s" % branches

        logger.debug(1, "Loading %s from %s" % ('branches', lindex['apilinks']['branches']))
        pindex['branches'] = _get_json_response(lindex['apilinks']['branches'] + filter,
                                                username=ud.user, password=ud.pswd)
        if not pindex['branches']:
            logger.debug(1, "No valid branches (%s) found at url %s." % (branches or "*", ud.url))
            return lindex
        lindex = add_raw_element("branches", layers.layerindex.Branch, pindex, lindex)


        # Load all of the layerItems (these can not be easily filtered)
        logger.debug(1, "Loading %s from %s" % ('layerItems', lindex['apilinks']['layerItems']))
        pindex['layerItems'] = _get_json_response(lindex['apilinks']['layerItems'],
                                                  username=ud.user, password=ud.pswd)
        if not pindex['layerItems']:
            logger.debug(1, "No layers were found at url %s." % (ud.url))
            return lindex
        lindex = add_raw_element("layerItems", layers.layerindex.LayerItem, pindex, lindex)


	# From this point on load the contents for each branch.  Otherwise we
	# could run into a timeout.
        for branch in lindex['branches']:
            filter = "?filter=branch__name:%s" % lindex['branches'][branch].get_name()

            logger.debug(1, "Loading %s from %s" % ('layerBranches', lindex['apilinks']['layerBranches']))
            pindex['layerBranches'] = _get_json_response(lindex['apilinks']['layerBranches'] + filter,
                                                  username=ud.user, password=ud.pswd)
            if not pindex['layerBranches']:
                logger.debug(1, "No valid layer branches (%s) found at url %s." % (branches or "*", ud.url))
                return lindex
            lindex = add_raw_element("layerBranches", layers.layerindex.LayerBranch, pindex, lindex)


            # Load the rest, they all have a similar format
            filter = "?filter=layerbranch__branch__name:%s" % lindex['branches'][branch].get_name()
            for (lName, lType) in [("layerDependencies", layers.layerindex.LayerDependency),
                                   ("recipes", layers.layerindex.Recipe),
                                   ("machines", layers.layerindex.Machine),
                                   ("distros", layers.layerindex.Distro)]:
                if lName not in load.split():
                    continue
                logger.debug(1, "Loading %s from %s" % (lName, lindex['apilinks'][lName]))
                pindex[lName] = _get_json_response(lindex['apilinks'][lName] + filter,
                                            username=ud.user, password=ud.pswd)
                lindex = add_raw_element(lName, lType, pindex, lindex)


        return lindex

    def store_index(self, ud, lindex):
        """
            Store layer information into a local file/dir.

            The return value is a dictionary containing API,
            layer, branch, dependency, recipe, machine, distro, information.

            ud is a parsed url to a directory or file.  If the path is a
            directory, we will split the files into one file per layer.
            If the path is to a file (exists or not) the entire DB will be
            dumped into that one file.
        """

        if ud.type != 'file':
            raise NotImplementedError('Writing to anything but a file url is not implemented: %s' % ud.url)

        # Write out to a single file, we have to sort the entries as we write
        if not os.path.isdir(ud.path):
            pindex = {}
            for entry in lindex:
                # Check for either locally added item or apilinks to ignore
                if entry in lindex['CONFIG']['local'] or \
                   entry == 'apilinks':
                    continue
                pindex[entry] = []
                for objId in lindex[entry]:
                    pindex[entry].append(lindex[entry][objId].data)

            bb.debug(1, 'Writing index to %s' % ud.path)
            json.dump(layers.layerindex.sort_entry(pindex), open(ud.path, 'wt'), indent=4)
            return

        # Write out to a directory one file per layerBranch
        try:
            layerBranches = lindex['layerBranches']
        except KeyError:
            logger.error('No layerBranches to write.')
            return

        for layerBranchId in layerBranches:
            pindex = {}

            def filter_item(layerBranchId, objects):
                filtered = []
                for obj in lindex[objects]:
                    try:
                        if lindex[objects][obj].get_layerbranch_id() == layerBranchId:
                            filtered.append(lindex[objects][obj].data)
                    except AttributeError:
                        logger.debug(1, 'No obj.get_layerbranch_id(): %s' % objects)
                        # No simple filter method, just include it...
                        try:
                            filtered.append(lindex[objects][obj].data)
                        except AttributeError:
                            logger.debug(1, 'No obj.data: %s %s' % (objects, type(obj)))
                            filtered.append(obj)
                return filtered

            for entry in lindex:
                # Skip local items, apilinks and items already processed
                if entry in lindex['CONFIG']['local'] or \
                   entry == 'apilinks' or \
                   entry == 'branches' or \
                   entry == 'layerBranches' or \
                   entry == 'layerItems':
                    continue
                pindex[entry] = filter_item(layerBranchId, entry)

            # Add the layer we're processing as the first one...
            pindex['branches'] = [layerBranches[layerBranchId].get_branch().data]
            pindex['layerItems'] = [layerBranches[layerBranchId].get_layer().data]
            pindex['layerBranches'] = [layerBranches[layerBranchId].data]

            # We also need to include the layerbranch for any dependencies...
            for layerDep in pindex['layerDependencies']:
                layerDependency = layers.layerindex.LayerDependency(lindex, layerDep)

                layerItem = layerDependency.get_dependency_layer()
                layerBranch = layerDependency.get_dependency_layerBranch()

                # We need to avoid duplicates...
                if layerItem.data not in pindex['layerItems']:
                    pindex['layerItems'].append(layerItem.data)

                if layerBranch.data not in pindex['layerBranches']:
                    pindex['layerBranches'].append(layerBranch.data)

            # apply mirroring adjustments here....

            fname = lindex['CONFIG']['DESCRIPTION'] + '__' + pindex['branches'][0]['name'] + '__' + pindex['layerItems'][0]['name']
            fname = fname.translate(str.maketrans('/ ', '__'))
            fpath = os.path.join(ud.path, fname)

            bb.debug(1, 'Writing index to %s' % fpath + '.json')
            json.dump(layers.layerindex.sort_entry(pindex), open(fpath + '.json', 'wt'), indent=4)
