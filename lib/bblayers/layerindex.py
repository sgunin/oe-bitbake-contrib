import layers.manager
import layers.layerindex

import argparse
import logging
import os
import subprocess

from bblayers.action import ActionPlugin

logger = logging.getLogger('bitbake-layers')


def plugin_init(plugins):
    return LayerIndexPlugin()


class LayerIndexPlugin(ActionPlugin):
    """Subcommands for interacting with the layer index.

    This class inherits ActionPlugin to get do_add_layer.
    """

    def do_layerindex_fetch(self, args):
        """Fetches a layer from a layer index along with its dependent layers, and adds them to conf/bblayers.conf.
"""

        def _construct_url(baseurl, branch):
            if baseurl[-1] != '/':
                baseurl += '/'
            baseurl += "api/"
            baseurl += ";type=restapi"

            if branch:
                baseurl += ";branch=%s" % branch

            return baseurl


        # General URL to use based on standard setting
        indexurl = self.tinfoil.config_data.getVar('BBLAYERS_LAYERINDEX_URL')

        if not indexurl:
            logger.error("Cannot get BBLAYERS_LAYERINDEX_URL")
            return 1

        layerManager = layers.manager.LayerManager(self.tinfoil.config_data, self.tinfoil.cooker)

        remoteIndex = layers.layerindex.LayerIndex(self.tinfoil.config_data)

        # Set the default...
        branch = self.tinfoil.config_data.getVar('LAYERSERIES_CORENAMES') or 'master'
        if args.branch:
            branch = args.branch

        logger.debug(1, 'Trying branch %s' % branch)
        try:
            remoteIndex.load_layerindex(_construct_url(indexurl, branch))
        except Exception:
            if branch == args.branch:
                logger.error('Branch %s is not available' % branch)
                return 1
            logger.debug(1, 'Falling back to branch master')
            remoteIndex.load_layerindex(_construct_url(indexurl, 'master'), reload=True)

        if remoteIndex.is_empty():
            return 1

        # If we want the display to include already downloaded
        # keep the following line, otherwise comment out.
        cookerIndex = layers.layerindex.LayerIndex(self.tinfoil.config_data)
        cookerIndex.load_layerindex('file://internal;type=cooker', load='layerDependencies')

        lIndex = cookerIndex + remoteIndex

        ignore_layers = []
        if args.ignore:
            ignore_layers.extend(args.ignore.split(','))

        layernames = ' '.join(args.layername)
        (dependencies, invalidnames) = lIndex.get_dependencies(names=layernames, ignores=ignore_layers)

        if invalidnames:
            for invaluename in invalidnames:
                logger.error('Layer "%s" not found in layer index' % invaluename)
            return 1
        logger.plain("%s  %s  %s" % ("Layer".ljust(49), "Git repository (branch)".ljust(54), "Subdirectory"))
        logger.plain('=' * 125)

        for deplayerbranch in dependencies:
            layerBranch = dependencies[deplayerbranch][0]

            # This is the local content, uncomment to hide local
            # layers from the display.
            #if layerBranch.index['CONFIG']['TYPE'] == 'cooker':
            #    continue

            layerDeps = dependencies[deplayerbranch][1:]

            requiredby = []
            recommendedby = []
            for dep in layerDeps:
                if dep.is_required():
                    requiredby.append(dep.get_layer().get_name())
                else:
                    recommendedby.append(dep.get_layer().get_name())

            logger.plain('%s %s %s' % (("%s:%s:%s" %
                                  (layerBranch.index['CONFIG']['DESCRIPTION'],
                                  layerBranch.get_branch().get_name(),
                                  layerBranch.get_layer().get_name())).ljust(50),
                                  ("%s (%s)" % (layerBranch.get_layer().get_vcs_url(),
                                  layerBranch.get_actual_branch())).ljust(55),
                                  layerBranch.get_vcs_subdir()
                                               ))
            if requiredby:
                logger.plain('  required by: %s' % ' '.join(requiredby))
            if recommendedby:
                logger.plain('  recommended by: %s' % ' '.join(recommendedby))

        if args.show_only != True:
            layerManager.setup(dependencies)
            layerManager.fetch()
            layerManager.unpack()
            layerManager.update_bblayers()

    def do_layerindex_show_depends(self, args):
        """Find layer dependencies from layer index.
"""
        args.show_only = True
        args.ignore = []
        self.do_layerindex_fetch(args)

    def register_commands(self, sp):
        parser_layerindex_fetch = self.add_command(sp, 'layerindex-fetch', self.do_layerindex_fetch, parserecipes=False)
        parser_layerindex_fetch.add_argument('-n', '--show-only', help='show dependencies and do nothing else', action='store_true')
        parser_layerindex_fetch.add_argument('-b', '--branch', help='branch name to fetch (default %(default)s)')
        parser_layerindex_fetch.add_argument('-i', '--ignore', help='assume the specified layers do not need to be fetched/added (separate multiple layers with commas, no spaces)', metavar='LAYER')
        parser_layerindex_fetch.add_argument('layername', nargs='+', help='layer to fetch')

        parser_layerindex_show_depends = self.add_command(sp, 'layerindex-show-depends', self.do_layerindex_show_depends, parserecipes=False)
        parser_layerindex_show_depends.add_argument('-b', '--branch', help='branch name to fetch (default %(default)s)')
        parser_layerindex_show_depends.add_argument('layername', nargs='+', help='layer to query')
