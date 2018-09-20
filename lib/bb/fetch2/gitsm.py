# ex:ts=4:sw=4:sts=4:et
# -*- tab-width: 4; c-basic-offset: 4; indent-tabs-mode: nil -*-
"""
BitBake 'Fetch' git submodules implementation

Inherits from and extends the Git fetcher to retrieve submodules of a git repository
after cloning.

SRC_URI = "gitsm://<see Git fetcher for syntax>"

See the Git fetcher, git://, for usage documentation.

NOTE: Switching a SRC_URI from "git://" to "gitsm://" requires a clean of your recipe.

"""

# Copyright (C) 2013 Richard Purdie
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import bb
from   bb.fetch2.git import Git
from   bb.fetch2 import runfetchcmd
from   bb.fetch2 import logger
from   bb.fetch2 import Fetch
from   bb.fetch2 import BBFetchException

class GitSM(Git):
    def supports(self, ud, d):
        """
        Check to see if a given url can be fetched with git.
        """
        return ud.type in ['gitsm']

    def uses_submodules(self, ud, d, wd):
        for name in ud.names:
            try:
                runfetchcmd("%s show %s:.gitmodules" % (ud.basecmd, ud.revisions[name]), d, quiet=True, workdir=wd)
                return True
            except bb.fetch.FetchError:
                pass
        return False

    def update_submodules(self, ud, d, allow_network):
        submodules = []
        paths = {}
        uris = {}
        local_paths = {}

        for name in ud.names:
            gitmodules = runfetchcmd("%s show %s:.gitmodules" % (ud.basecmd, ud.revisions[name]), d, quiet=True, workdir=ud.clonedir)

            module = ""
            for line in gitmodules.splitlines():
                if line.startswith('[submodule'):
                    module = line.split('"')[1]
                    submodules.append(module)
                elif module and line.strip().startswith('path'):
                    path = line.split('=')[1].strip()
                    paths[module] = path
                elif module and line.strip().startswith('url'):
                    url = line.split('=')[1].strip()
                    uris[module] = url

        for module in submodules:
            module_hash = runfetchcmd("%s ls-tree -z -d %s %s" % (ud.basecmd, ud.revisions[name], paths[module]), d, quiet=True, workdir=ud.clonedir)
            module_hash = module_hash.split()[2]

            try:
                url = uris[module]
                if url.startswith('http:'):
                    url = url.replace('http:', 'git:', 1) + ';protocol=http'
                elif url.startswith('https:'):
                    url = url.replace('https:', 'git:', 1) + ';protocol=https'
                elif url.startswith('ssh:'):
                    url = url.replace('ssh:', 'git:', 1) + ';protocol=ssh'
                elif url.startswith('rsync:'):
                    url = url.replace('rsync:', 'git:', 1) + ';protocol=https'
                url += ";bareclone=1;nocheckout=1;name=%s" % (module)
                ld = d.createCopy()
                ld.setVar('SRCREV', module_hash)
                ld.setVar('SRCPV', d.getVar('SRCPV'))
                ld.setVar('SRCREV_FORMAT', module)
                ld.setVar('SRC_URI', url)
                newfetch = Fetch([url], ld)
                newfetch.download()
                local_paths[module] = newfetch.localpath(url)

                # Correct the submodule references to the local download version...
                bb.warn("%(basecmd)s config submodule.%(module)s.url %(url)s" % {'basecmd': ud.basecmd, 'module': module, 'url' : local_paths[module]})
                runfetchcmd("%(basecmd)s config submodule.%(module)s.url %(url)s" % {'basecmd': ud.basecmd, 'module': module, 'url' : local_paths[module]}, d, workdir=ud.clonedir)
                try:
                    os.mkdir(os.path.join(ud.clonedir, 'modules'))
                except OSError:
                    pass
                os.symlink(local_paths[module], os.path.join(ud.clonedir, 'modules', paths[module]))

            except BBFetchException as e:
                bb.error(str(e))

        return True

    def need_update(self, ud, d):
        main_repo_needs_update = Git.need_update(self, ud, d)

        # First check that the main repository has enough history fetched. If it doesn't, then we don't
        # even have the .gitmodules and gitlinks for the submodules to attempt asking whether the
        # submodules' histories are recent enough.
        if main_repo_needs_update:
            return True

        # Now check that the submodule histories are new enough. The git-submodule command doesn't have
        # any clean interface for doing this aside from just attempting the checkout (with network
        # fetched disabled).
        return not self.update_submodules(ud, d, allow_network=False)

    def download(self, ud, d):
        Git.download(self, ud, d)

        if not ud.shallow or ud.localpath != ud.fullshallow:
            submodules = self.uses_submodules(ud, d, ud.clonedir)
            if submodules:
                self.update_submodules(ud, d, allow_network=False)

    def clone_shallow_local(self, ud, dest, d):
        super(GitSM, self).clone_shallow_local(ud, dest, d)

        runfetchcmd('cp -fpLR "%s/modules" "%s/"' % (ud.clonedir, os.path.join(dest, '.git')), d)

    def unpack(self, ud, destdir, d):
        Git.unpack(self, ud, destdir, d)

        if self.uses_submodules(ud, d, ud.destdir):
            runfetchcmd(ud.basecmd + " checkout " + ud.revisions[ud.names[0]], d, workdir=ud.destdir)

            # Copy over the submodules' fetched histories too.
            if ud.bareclone:
                repo_conf = ud.destdir
            else:
                repo_conf = os.path.join(ud.destdir, '.git')

            if os.path.exists(os.path.join(ud.clonedir, 'modules')):
                # This is not a copy unpacked from a shallow mirror clone. So
                # the manual intervention to populate the .git/modules done
                # in clone_shallow_local() won't have been done yet.
                bb.warn('cp -fpLR')
                runfetchcmd("cp -fpLR %s %s" % (os.path.join(ud.clonedir, 'modules'), repo_conf), d)
            elif os.path.exists(os.path.join(repo_conf, 'modules')):
                # Unpacked from a shallow mirror clone. Manual population of
                # .git/modules is already done.
                bb.warn('shallow mirror')
                pass
            else:
                # This is fatal; git-submodule would fetch it, but that is not allowed
                raise bb.fetch2.FetchError("submodule contents not retrieved during do_fetch()")

        submodules = []
        paths = {}
        uris = {}
        local_paths = {}
        for name in ud.names:
            gitmodules = runfetchcmd("%s show HEAD:.gitmodules" % (ud.basecmd), d, quiet=True, workdir=ud.destdir)
            bb.warn('gitmodules: %s' % gitmodules)

            module = ""
            for line in gitmodules.splitlines():
                if line.startswith('[submodule'):
                    module = line.split('"')[1]
                    submodules.append(module)
                elif module and line.strip().startswith('path'):
                    path = line.split('=')[1].strip()
                    paths[module] = path
                elif module and line.strip().startswith('url'):
                    url = line.split('=')[1].strip()
                    uris[module] = url

        for module in submodules:
            modpath = os.path.join(repo_conf, 'modules', module)

            # Determine (from the submodule) the correct url to reference
            bb.warn('%s: %s' % (modpath, "%(basecmd)s config remote.origin.url" % {'basecmd': ud.basecmd}))
            local_paths[module] = runfetchcmd("%(basecmd)s config remote.origin.url" % {'basecmd': ud.basecmd}, d, workdir=modpath)

            # Setup the local URL properly (like git submodule init or sync would do...)
            runfetchcmd("%(basecmd)s config submodule.%(module)s.url %(url)s" % {'basecmd': ud.basecmd, 'module': module, 'url' : local_paths[module]}, d, workdir=ud.destdir)

            # Ensure the submodule repository is NOT set to bare, since we're checking it out...
            runfetchcmd("%s config core.bare false" % (ud.basecmd), d, quiet=True, workdir=modpath)

        # Run submodule update, this sets up the directories -- without touching the config
        runfetchcmd("%s submodule update --no-fetch" % (ud.basecmd), d, quiet=True, workdir=ud.destdir)
