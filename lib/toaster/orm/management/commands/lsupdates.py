#
# ex:ts=4:sw=4:sts=4:et
# -*- tab-width: 4; c-basic-offset: 4; indent-tabs-mode: nil -*-
#
# BitBake Toaster Implementation
#
# Copyright (C) 2016-2017   Intel Corporation
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

from django.core.management.base import BaseCommand

from orm.models import LayerSource, Layer, Release, Layer_Version
from orm.models import LayerVersionDependency, Machine, Recipe
from orm.models import Distro

import os
import sys

import logging
import threading
import time
logger = logging.getLogger("toaster")

DEFAULT_LAYERINDEX_SERVER = "http://layers.openembedded.org/layerindex/api/;type=restapi"

# load Bitbake components
path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, path)


class Spinner(threading.Thread):
    """ A simple progress spinner to indicate download/parsing is happening"""
    def __init__(self, *args, **kwargs):
        super(Spinner, self).__init__(*args, **kwargs)
        self.setDaemon(True)
        self.signal = True

    def run(self):
        os.system('setterm -cursor off')
        while self.signal:
            for char in ["/", "-", "\\", "|"]:
                sys.stdout.write("\r" + char)
                sys.stdout.flush()
                time.sleep(0.25)
        os.system('setterm -cursor on')

    def stop(self):
        self.signal = False


class Command(BaseCommand):
    args = ""
    help = "Updates locally cached information from a layerindex server"

    def mini_progress(self, what, i, total):
        i = i + 1
        pec = (float(i)/float(total))*100

        sys.stdout.write("\rUpdating %s %d%%" %
                         (what,
                          pec))
        sys.stdout.flush()
        if int(pec) is 100:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def update(self):
        """
            Fetches layer, recipe and machine information from a layerindex
            server
        """
        os.system('setterm -cursor off')

        self.apiurl = DEFAULT_LAYERINDEX_SERVER

        assert self.apiurl is not None

        # update branches; only those that we already have names listed in the
        # Releases table
        whitelist_branch_names = [rel.branch_name
                                  for rel in Release.objects.all()]
        if len(whitelist_branch_names) == 0:
            raise Exception("Failed to make list of branches to fetch")

        self.apiurl += ";branch=%s" % "OR".join(whitelist_branch_names)

        http_progress = Spinner()

        logger.info("Fetching metadata releases for %s",
                    " ".join(whitelist_branch_names))


        import layers.layerindex

        layerindex = layers.layerindex.LayerIndex(None)

        http_progress.start()
        layerindex.load_layerindex(self.apiurl)
        http_progress.stop()

        # We know we're only processing one entry, so we reference it here
        # (this is cheating...)
        lindex = layerindex.lindex[0]

        # Map the layer index branches to toaster releases
        li_branch_id_to_toaster_release = {}

        logger.info("Processing branches")

        total = len(lindex['branches'])
        for i, branchId in enumerate(lindex['branches']):
            li_branch_id_to_toaster_release[branchId] = \
                    Release.objects.get(name=lindex['branches'][branchId].get_name())
            self.mini_progress("Releases", i, total)

        # keep a track of the layerindex (li) id mappings so that
        # layer_versions can be created for these layers later on
        li_layer_id_to_toaster_layer_id = {}

        logger.info("Processing layers")

        total = len(lindex['layerItems'])
        for i, liId in enumerate(lindex['layerItems']):
            try:
                l, created = Layer.objects.get_or_create(name=lindex['layerItems'][liId].get_name())
                l.up_date = lindex['layerItems'][liId].get_updated()
                l.summary = lindex['layerItems'][liId].get_summary()
                l.description = lindex['layerItems'][liId].get_description()

                if created:
                    l.vcs_url = lindex['layerItems'][liId].get_vcs_url()
                    l.vcs_web_url = lindex['layerItems'][liId].get_vcs_web_url()
                    l.vcs_web_tree_base_url = lindex['layerItems'][liId].get_vcs_web_tree_base_url()
                    l.vcs_web_file_base_url = lindex['layerItems'][liId].get_vcs_web_file_base_url()
                l.save()
            except Layer.MultipleObjectsReturned:
                logger.info("Skipped %s as we found multiple layers and "
                            "don't know which to update" %
                            li['name'])

            li_layer_id_to_toaster_layer_id[liId] = l.pk

            self.mini_progress("layers", i, total)

        # update layer_versions
        logger.info("Provessing layer branches")

        # Map Layer index layer_branch object id to
        # layer_version toaster object id
        li_layer_branch_id_to_toaster_lv_id = {}

        total = len(lindex['layerBranches'])
        for i, lbiId in enumerate(lindex['layerBranches']):
            # release as defined by toaster map to layerindex branch
            release = li_branch_id_to_toaster_release[lindex['layerBranches'][lbiId].get_branch_id()]

            try:
                lv, created = Layer_Version.objects.get_or_create(
                    layer=Layer.objects.get(
                        pk=li_layer_id_to_toaster_layer_id[lindex['layerBranches'][lbiId].get_layer_id()]),
                    release=release
                )
            except KeyError:
                logger.warning(
                    "No such layerindex layer referenced by layerbranch %d" %
                    lindex['layerBranches'][lbiId].get_layer_id())
                continue

            if created:
                lv.release = li_branch_id_to_toaster_release[lindex['layerBranches'][lbiId].get_branch_id()]
                lv.up_date = lindex['layerBranches'][lbiId].get_updated()
                lv.commit = lindex['layerBranches'][lbiId].get_actual_branch()
                lv.dirpath = lindex['layerBranches'][lbiId].get_vcs_subdir()
                lv.save()

            li_layer_branch_id_to_toaster_lv_id[lindex['layerBranches'][lbiId].get_id()] =\
                lv.pk
            self.mini_progress("layer versions", i, total)

        logger.info("Processing layer dependencies")

        dependlist = {}
        for ldiId in lindex['layerDependencies']:
            try:
                lv = Layer_Version.objects.get(
                    pk=li_layer_branch_id_to_toaster_lv_id[lindex['layerDependencies'][ldiId].get_layerbranch_id()])
            except Layer_Version.DoesNotExist as e:
                continue

            if lv not in dependlist:
                dependlist[lv] = []
            try:
                layer_id = li_layer_id_to_toaster_layer_id[lindex['layerDependencies'][ldiId].get_dependency_id()]

                dependlist[lv].append(
                    Layer_Version.objects.get(layer__pk=layer_id,
                                              release=lv.release))

            except Layer_Version.DoesNotExist:
                logger.warning("Cannot find layer version (ls:%s),"
                               "up_id:%s lv:%s" %
                               (self, lindex['layerDependencies'][ldiId].get_dependency_id(), lv))

        total = len(dependlist)
        for i, lv in enumerate(dependlist):
            LayerVersionDependency.objects.filter(layer_version=lv).delete()
            for lvd in dependlist[lv]:
                LayerVersionDependency.objects.get_or_create(layer_version=lv,
                                                             depends_on=lvd)
            self.mini_progress("Layer version dependencies", i, total)

        # update Distros
        logger.info("Processing distro information")

        total = len(lindex['distros'])
        for i, diId in enumerate(lindex['distros']):
            distro, created = Distro.objects.get_or_create(
                name=lindex['distros'][diId].get_name(),
                layer_version=Layer_Version.objects.get(
                    pk=li_layer_branch_id_to_toaster_lv_id[lindex['distros'][diId].get_layerbranch_id()]))
            distro.up_date = lindex['distros'][diId].get_updated()
            distro.name = lindex['distros'][diId].get_name()
            distro.description = lindex['distros'][diId].get_description()
            distro.save()
            self.mini_progress("distros", i, total)

        # update machines
        logger.info("Processing machine information")

        total = len(lindex['machines'])
        for i, miId in enumerate(lindex['machines']):
            mo, created = Machine.objects.get_or_create(
                name=lindex['machines'][miId].get_name(),
                layer_version=Layer_Version.objects.get(
                    pk=li_layer_branch_id_to_toaster_lv_id[lindex['machines'][miId].get_layerbranch_id()]))
            mo.up_date = lindex['machines'][miId].get_updated()
            mo.name = lindex['machines'][miId].get_name()
            mo.description = lindex['machines'][miId].get_description()
            mo.save()
            self.mini_progress("machines", i, total)

        # update recipes; paginate by layer version / layer branch
        logger.info("Processing recipe information")

        total = len(lindex['recipes'])
        for i, riId in enumerate(lindex['recipes']):
            try:
                lv_id = li_layer_branch_id_to_toaster_lv_id[lindex['recipes'][riId].get_layerbranch_id()]
                lv = Layer_Version.objects.get(pk=lv_id)

                ro, created = Recipe.objects.get_or_create(
                    layer_version=lv,
                    name=lindex['recipes'][riId].get_pn()
                )

                ro.layer_version = lv
                ro.up_date = lindex['recipes'][riId].get_updated()
                ro.name = lindex['recipes'][riId].get_pn()
                ro.version = lindex['recipes'][riId].get_pv()
                ro.summary = lindex['recipes'][riId].get_summary()
                ro.description = lindex['recipes'][riId].get_description()
                ro.section = lindex['recipes'][riId].get_section()
                ro.license = lindex['recipes'][riId].get_license()
                ro.homepage = lindex['recipes'][riId].get_homepage()
                ro.bugtracker = lindex['recipes'][riId].get_bugtracker()
                ro.file_path = lindex['recipes'][riId].get_filepath() + "/" + lindex['recipes'][riId].get_filename()
                ro.is_image = 'image' in lindex['recipes'][riId].get_inherits().split()
                ro.save()
            except Exception as e:
                logger.warning("Failed saving recipe %s", e)

            self.mini_progress("recipes", i, total)

        os.system('setterm -cursor on')

    def handle(self, **options):
        self.update()
