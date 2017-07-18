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
import os
import bb.msg

logger = logging.getLogger('BitBake.layerindex.common')

class LayerManagerError(Exception):
    """LayerManager error"""
    def __init__(self, message):
         self.msg = message
         Exception.__init__(self, message)

    def __str__(self):
         return self.msg

class DownloadPlugin():
    def __init__(self, manager):
        self.type = None

    def init(self, manager):
        self.manager = manager
        self.data = self.manager.data

    def plugin_type(self):
        return self.type

    def setup(self, layers, ignore):
        """Setup the download"""

        raise NotImplementedError('setup is not implemented')

    def fetch(self):
        """Fetch the layers from setup"""

        raise NotImplementedError('fetch is not implemented')

    def unpack(self):
        """Fetch the layers from setup"""

        raise NotImplementedError('fetch is not implemented')

    def get_new_layers(self):
        """Return a list of layers that we've unpacked"""

        raise NotImplementedError('get_new_layers is not implemented')
