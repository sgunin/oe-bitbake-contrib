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
import json

from collections import OrderedDict, defaultdict

from urllib.parse import unquote, urlparse

import layerindexlib

import layerindexlib.plugin

logger = logging.getLogger('BitBake.layerindexlib.cooker')

import bb.utils

def plugin_init(plugins):
    return CookerPlugin()

class CookerPlugin(layerindexlib.plugin.IndexPlugin):
    def __init__(self):
        self.type = "cooker"

        self.server_connection = None
        self.ui_module = None
        self.server = None

    def load_index(self, url, load):
        """
            Fetches layer information from a build configuration.

            The return value is a dictionary containing API,
            layer, branch, dependency, recipe, machine, distro, information.

            url type should be 'cooker'.
            url path is ignored
        """

        up = urlparse(url)

        if up.scheme != 'cooker':
            raise layerindexlib.plugin.LayerIndexPluginUrlError(self.type, url)

        d = self.layerindex.data

        params = self.layerindex._parse_params(up.params)

        # Only reason to pass a branch is to emulate them...
        if 'branch' in params:
            branches = params['branch'].split(',')
        else:
            branches = ['HEAD']

        logger.debug(1, "Loading cooker data branches %s" % branches)

        import bblayerlib
        bblayers = bblayerlib.BBLayers(d)
        index = bblayers.load_bblayers(branches=branches)

        index.config = {}
        index.config['TYPE'] = self.type
        index.config['URL'] = url

        if 'desc' in params:
            index.config['DESCRIPTION'] = unquote(params['desc'])
        else:
            index.config['DESCRIPTION'] = 'local'

        if 'cache' in params:
            index.config['CACHE'] = params['cache']

        index.config['BRANCH'] = branches

        if 'layerDependencies' in load:
            index = bblayers.load_layerDependencies()

        if False and 'recipes' in load:
            # Requires server access, which we don't have
            index = bblayers.load_recipes(server)

        if 'machines' in load:
            index = bblayers.load_machines()

        if 'distros' in load:
            index = bblayers.load_distros()

        return index
