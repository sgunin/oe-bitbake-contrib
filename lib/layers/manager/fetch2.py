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

from layers.manager.common import DownloadPlugin

import logging
import bb.fetch2

import layers.layerindex

logger = logging.getLogger('BitBake.layers.manager.fetch2')

def plugin_init(plugins):
    return Fetch2Plugin()

class Fetch2Plugin(DownloadPlugin):
    def __init__(self):
        self.type = "fetch2"

    def setup(self):
        if not self.manager:
            raise Exception('plugin was not initialized properly.')

        local_index = self.manager.local_index
        layers = self.manager.layers
        ignore = self.manager.ignore

        def gen_src_uri(uri, branch):
            type, path = uri.split('://', 1)
            return 'git://%s;protocol=%s;branch=%s;rev=%s' % (path, type, branch, branch)

        # Format:
        # url[<vcs_url>] = [ <src_uri>, layer_name1, layer_name2, ... layer_name3 ]
        local_urls = {}
        for layerBranchId in local_index['layerBranches']:
            layerBranch = local_index['layerBranches'][layerBranchId]
            url = layerBranch.get_layer().get_vcs_url()
            if url not in local_urls:
                local_urls[url] = [gen_src_uri(url, layerBranch.get_branch().get_name())]
            if layerBranch.get_layer().get_name() not in local_urls[url]:
                local_urls[url].append(layerBranch.get_layer().get_name())

        remote_urls = {}
        for deplayerbranch in layers:
            layerBranch = layers[deplayerbranch][0]
            url = layerBranch.get_layer().get_vcs_url()
            if url not in local_urls:
                if url not in remote_urls:
                    remote_urls[url] = [gen_src_uri(url, layerBranch.get_branch().get_name())]
                if layerBranch.get_layer().get_name() not in remote_urls[url]:
                    remote_urls[url].append(layerBranch.get_layer().get_name())

        self.local_urls = local_urls
        self.remote_urls = remote_urls

        #self.debug()

        # define defaults here...

        src_uri = ""
        for url in remote_urls:
            src_uri += " " + remote_urls[url][0] + ";destsuffix=%s" % os.path.basename(url).rstrip('.git')

        self.src_uri = src_uri.strip()


    def fetch(self):
        src_uri = self.src_uri
        if not src_uri:
            # Nothing to fetch
            self.fetcher = None
            return

        logger.plain('Fetching...')

        remote_urls = self.remote_urls
        localdata = self.manager.data.createCopy()

        fetchdir = localdata.getVar('BBLAYERS_FETCH_DIR')

        localdata.setVar('SRC_URI', src_uri)

        localdata.delVar('MIRRORS')
        localdata.delVar('PREMIRRORS')
        mirrors = localdata.getVar('BBLAYERS_MIRRORS')
        if mirrors:
            localdata.setVar('PREMIRRORS', mirrors)

        dldir = localdata.getVar('BBLAYERS_DL_DIR')
        if not dldir:
            dldir = os.path.join(fetchdir, '_layers')
        localdata.setVar('DL_DIR', dldir)
        localdata.setVar('FILESPATH', dldir)

        if localdata.getVar('BB_NO_NETWORK') == '1' and localdata.getVar('BBLAYERS_ALLOW_NETWORK'):
            localdata.delVar('BB_NO_NETWORK')

        self.fetcher = bb.fetch2.Fetch(src_uri.split(), localdata, cache=False)
        self.fetcher.download()

    def unpack(self):
        if not self.fetcher:
            # Nothing to unpack
            return

        logger.plain('Unpacking...')
        fetchdir = self.manager.data.getVar('BBLAYERS_FETCH_DIR')
        self.fetcher.unpack(fetchdir)

    def get_new_layers(self):
        layers = self.manager.layers
        remote_urls = self.remote_urls

        fetchdir = self.manager.data.getVar('BBLAYERS_FETCH_DIR')

        new_layers = []

        local_layers = []
        local_index = self.manager.local_index
        for layerBranchId in local_index['layerBranches']:
            layerBranch = local_index['layerBranches'][layerBranchId]
            local_layers.append(layerBranch.get_layer().get_name())

        for deplayerbranch in layers:
            layerBranch = layers[deplayerbranch][0]
            if layerBranch.get_layer().get_name() in local_layers:
                # We already have it
                continue

            path = os.path.join(fetchdir,
                                os.path.basename(layerBranch.get_layer().get_vcs_url()).rstrip('.git'),
                                layerBranch.get_vcs_subdir() or "")

            if not os.path.isdir(path):
                raise Exception('Expected layer path %s does not exist.' % path)
                continue

            new_layers.append(path)

        return new_layers


    def debug(self):
        #### Debugging
        layers = self.manager.layers
        remote_urls = self.remote_urls

        logger.plain("%s  %s  %s" % ("Layer".ljust(24), "Git repository (branch)".ljust(54), "Subdirectory"))
        logger.plain('=' * 105)

        for deplayerbranch in layers:
            layerBranch = layers[deplayerbranch][0]
            layerDeps = layers[deplayerbranch][1:]

            requiredby = []
            recommendedby = []
            for dep in layerDeps:
                if dep.is_required():
                    requiredby.append(dep.get_layer().get_name())
                else:
                    recommendedby.append(dep.get_layer().get_name())

            required = False
            if (not requiredby and not recommendedby) or requiredby:
                required = True

            logger.plain('%s%s %s %s' % (
                                  [' ', '+'][layerBranch.get_layer().get_vcs_url() in remote_urls],
                                  layerBranch.get_layer().get_name().ljust(24),
                                  ("%s (%s)" % (layerBranch.get_layer().get_vcs_url(),
                                  layerBranch.get_actual_branch())).ljust(55),
                                  layerBranch.get_vcs_subdir()
                                               ))
        #### Debugging
