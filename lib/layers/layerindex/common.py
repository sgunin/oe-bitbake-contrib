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

import argparse
import logging
import os
import bb.msg

logger = logging.getLogger('BitBake.layerindex.common')

class LayerIndexError(Exception):
    """LayerIndex loading error"""
    def __init__(self, message):
         self.msg = message
         Exception.__init__(self, message)

    def __str__(self):
         return self.msg

class IndexPlugin():
    def __init__(self):
        self.type = None

    def init(self, lindex):
        self.lindex = lindex

    def plugin_type(self):
        return self.type

    def load_index(self, uri):
        raise NotImplementedError('load_index is not implemented')

    def store_index(self, uri):
        raise NotImplementedError('store_index is not implemented')

# Fetch something from a specific URL.  This is specifically designed to
# fetch data from a layer index or related element.  It should NOT be
# used to fetch recipe contents or similar.
#
# TODO: Handle BB_NO_NETWORK or allowed hosts, etc.
#
def fetch_url(url, username=None, password=None, debuglevel=0):
    assert url is not None

    import urllib
    from urllib.request import urlopen, Request
    from urllib.parse import urlparse

    up = urlparse(url)

    if username:
        logger.debug(1, "Configuring authentication for %s..." % url)
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, "%s://%s" % (up.scheme, up.netloc), username, password)
        handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(debuglevel=debuglevel))
    else:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(debuglevel=debuglevel))

    urllib.request.install_opener(opener)

    logger.debug(1, "Fetching %s (%s)..." % (url, ["without authentication", "with authentication"][not not username]))

    try:
        res = urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 (bitbake/lib/layerindex)'}, unverifiable=True))
    except urllib.error.HTTPError as e:
        logger.debug(1, "HTTP Error: %s: %s" % (e.code, e.reason))
        logger.debug(1, " Requested: %s" % (url))
        logger.debug(1, " Actual:    %s" % (e.geturl()))

        if e.code == 404:
            logger.debug(1, "Request not found.")
            raise bb.fetch2.FetchError(e)
        else:
            logger.debug(1, "Headers:\n%s" % (e.headers))
            raise bb.fetch2.FetchError(e)
    except OSError as e:
        error = 0
        reason = ""

        # Process base OSError first...
        if hasattr(e, 'errno'):
            error = e.errno
            reason = e.strerror

        # Process gaierror (socket error) subclass if available.
        if hasattr(e, 'reason') and hasattr(e.reason, 'errno') and hasattr(e.reason, 'strerror'):
            error = e.reason.errno
            reason = e.reason.strerror
            if error == -2:
                raise bb.fetch2.FetchError(e)

        if error and error != 0:
            raise bb.fetch2.FetchError("Unable to fetch %s due to exception: [Error %s] %s" % (url, error, reason))
        else:
            raise bb.fetch2.FetchError("Unable to fetch %s due to OSError exception: %s" % (url, e))

    finally:
        logger.debug(1, "...fetching %s (%s), done." % (url, ["without authentication", "with authentication"][not not username]))

    return res

# Add a raw object of type lType to lindex[lname]
def add_raw_element(lName, lType, rawObjs, lindex):
    if lName not in rawObjs:
        logger.debug(1, '%s not in loaded index' % lName)
        return lindex

    if lName not in lindex:
        lindex[lName] = {}

    for entry in rawObjs[lName]:
        obj = lType(lindex, entry)
        if obj.get_id() in lindex[lName]:
            if lindex[lName][obj.get_id()] == obj:
                continue
            raise Exception('Conflict adding object %s(%s)' % (lName, obj.get_id()))
        lindex[lName][obj.get_id()] = obj

    return lindex

# Add a layer index object to lindex[lName]
def add_element(lName, Objs, lindex):
    if lName not in lindex:
        lindex[lName] = {}

    for obj in Objs:
        if obj.get_id() in lindex[lName]:
            if lindex[lName][obj.get_id()] == obj:
                continue
            raise Exception('Conflict adding object %s(%s)' % (lName, obj.get_id()))
        lindex[lName][obj.get_id()] = obj

    return lindex
