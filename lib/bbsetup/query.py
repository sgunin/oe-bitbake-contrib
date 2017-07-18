import collections
import fnmatch
import logging
import sys
import os
import re

import bb.utils

from bbsetup.common import SetupPlugin

import layers.layerindex

logger = logging.getLogger('BitBake.BBSetup.query')

def plugin_init(plugins):
    return QueryPlugin()


class QueryPlugin(SetupPlugin):
    def do_query(self, args):
        """Query the layer index"""
        lindex = layers.layerindex.LayerIndex(self.data)

        loadMask = ""
        if args.layerdependencies:
            loadMask += " layerDependencies"

        if args.recipes:
            loadMask += " recipes"

        if args.machines:
            loadMask += " machines"

        if args.distros:
            loadMask += " distros"

        lindex.load_layerindex(self.data.getVar('BBLAYERINDEX_URI'), load=loadMask)

        if args.distros:
            lindex.list_obj('distros')

        if args.machines:
            lindex.list_obj('machines')

        if args.branches:
            lindex.list_obj('branches')

        if args.layers:
            lindex.list_obj('layerItems')

        if args.layerbranches:
            lindex.list_obj('layerBranches')

        if args.layerdependencies:
            lindex.list_obj('layerDependencies')

        if args.recipes:
            lindex.list_obj('recipes')

        #lindex.store_layerindex('file:///tmp/wr-index;type=restapi', lindex.lindex[0])
        #lindex.store_layerindex('file:///tmp/oe-index;type=restapi', lindex.lindex[1])
        #lindex.store_layerindex('file:///tmp/test-api.json;type=restapi', lindex.lindex[0])

    def register_commands(self, sp):
        query = self.add_command(sp, 'query', self.do_query)

        query.add_argument('--distros', help='List all available distro values', action='store_true')
        query.add_argument('--machines', help='List all available machine values', action='store_true')
        query.add_argument('--branches', help='List all available branch values', action='store_true')
        query.add_argument('--layers', help='List all available layers', action='store_true')
        query.add_argument('--layerbranches', help='List all available layerbranches', action='store_true')
        query.add_argument('--layerdependencies', help='List all available layerdependencies', action='store_true')
        query.add_argument('--recipes', help='List all available recipe values', action='store_true')

