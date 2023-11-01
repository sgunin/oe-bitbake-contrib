#! /usr/bin/env python3
#
# BitBake Toaster UI tests implementation
#
# Copyright (C) 2023 Savoir-faire Linux Inc
#
# SPDX-License-Identifier: GPL-2.0-only
#

import re
import pytest
from django.urls import reverse
from selenium.webdriver.support.ui import Select
from tests.functional.functional_helpers import SeleniumFunctionalTestCase
from orm.models import Project
from selenium.webdriver.common.by import By

@pytest.mark.django_db
class TestCreateNewProject(SeleniumFunctionalTestCase):

    def test_create_new_project_master(self):
        """ Test create new project using:
          - Project Name: Any string
          - Release: Yocto Project master (option value: 3)
          - Merge Toaster settings: False
        """
        release = 'Yocto Project master'
        project_name = 'projectmaster'
        self.get(reverse('newproject'))
        self.driver.find_element(By.ID,
                                 "new-project-name").send_keys(project_name)

        select = Select(self.find('#projectversion'))
        select.select_by_value(str(3))

        # uncheck merge toaster settings
        checkbox = self.find('.checkbox-mergeattr')
        if checkbox.is_selected():
            checkbox.click()

        self.driver.find_element(By.ID, "create-project-button").click()

        element = self.wait_until_visible('#project-created-notification')
        self.assertTrue(self.element_exists('#project-created-notification'),
                        'Project creation notification not shown')
        self.assertTrue(project_name in element.text,
                        "New project name not in new project notification")
        self.assertTrue(Project.objects.filter(name=project_name).count(),
                        "New project not found in database")

        # check release
        self.assertTrue(re.search(
            release,
            self.driver.find_element(By.XPATH,
                                     "//span[@id='project-release-title']"
                                     ).text),
                        'The project release is not defined')

    def test_create_new_project_mickledore(self):
        """ Test create new project using:
          - Project Name: Any string
          - Release: Yocto Project 4.2 "Mickledore" (option value: 4)
          - Merge Toaster settings: True
        """
        release = 'Yocto Project 4.2 "Mickledore"'
        project_name = 'projectmickledore'
        self.get(reverse('newproject'))
        self.driver.find_element(By.ID,
                                 "new-project-name").send_keys(project_name)

        select = Select(self.find('#projectversion'))
        select.select_by_value(str(4))

        # check merge toaster settings
        checkbox = self.find('.checkbox-mergeattr')
        if not checkbox.is_selected():
            checkbox.click()

        self.driver.find_element(By.ID, "create-project-button").click()

        element = self.wait_until_visible('#project-created-notification')
        self.assertTrue(self.element_exists('#project-created-notification'),
                        'Project creation notification not shown')
        self.assertTrue(project_name in element.text,
                        "New project name not in new project notification")
        self.assertTrue(Project.objects.filter(name=project_name).count(),
                        "New project not found in database")

        # check release
        self.assertTrue(re.search(
            release,
            self.driver.find_element(By.XPATH,
                                     "//span[@id='project-release-title']"
                                     ).text),
                        'The project release is not defined')

    def test_create_new_project_kirkstone(self):
        """ Test create new project using:
          - Project Name: Any string
          - Release: Yocto Project 4.0 "Kirkstone" (option value: 1)
          - Merge Toaster settings: True
        """
        release = 'Yocto Project 4.0 "Kirkstone"'
        project_name = 'projectkirkstone'
        self.get(reverse('newproject'))
        self.driver.find_element(By.ID,
                                 "new-project-name").send_keys(project_name)

        select = Select(self.find('#projectversion'))
        select.select_by_value(str(1))

        # check merge toaster settings
        checkbox = self.find('.checkbox-mergeattr')
        if not checkbox.is_selected():
            checkbox.click()

        self.driver.find_element(By.ID,
                                 "create-project-button").click()

        element = self.wait_until_visible('#project-created-notification')
        self.assertTrue(self.element_exists('#project-created-notification'),
                        'Project creation notification not shown')
        self.assertTrue(project_name in element.text,
                        "New project name not in new project notification")
        self.assertTrue(Project.objects.filter(name=project_name).count(),
                        "New project not found in database")

        # check release
        self.assertTrue(re.search(
            release,
            self.driver.find_element(By.XPATH,
                                     "//span[@id='project-release-title']"
                                     ).text),
                        'The project release is not defined')

    def test_create_new_project_dunfull(self):
        """ Test create new project using:
          - Project Name: Any string
          - Release: Yocto Project 3.1 "Dunfell" (option value: 5)
          - Merge Toaster settings: False
        """
        release = 'Yocto Project 3.1 "Dunfell"'
        project_name = 'projectdunfull'
        self.get(reverse('newproject'))
        self.driver.find_element(By.ID,
                                 "new-project-name").send_keys(project_name)

        select = Select(self.find('#projectversion'))
        select.select_by_value(str(5))

        # check merge toaster settings
        checkbox = self.find('.checkbox-mergeattr')
        if checkbox.is_selected():
            checkbox.click()

        self.driver.find_element(By.ID, "create-project-button").click()

        element = self.wait_until_visible('#project-created-notification')
        self.assertTrue(self.element_exists('#project-created-notification'),
                        'Project creation notification not shown')
        self.assertTrue(project_name in element.text,
                        "New project name not in new project notification")
        self.assertTrue(Project.objects.filter(name=project_name).count(),
                        "New project not found in database")

        # check release
        self.assertTrue(re.search(
            release,
            self.driver.find_element(By.XPATH,
                                     "//span[@id='project-release-title']"
                                     ).text),
                        'The project release is not defined')

    def test_create_new_project_local(self):
        """ Test create new project using:
          - Project Name: Any string
          - Release: Local Yocto Project (option value: 2)
          - Merge Toaster settings: True
        """
        release = 'Local Yocto Project'
        project_name = 'projectlocal'
        self.get(reverse('newproject'))
        self.driver.find_element(By.ID,
                                 "new-project-name").send_keys(project_name)

        select = Select(self.find('#projectversion'))
        select.select_by_value(str(2))

        # check merge toaster settings
        checkbox = self.find('.checkbox-mergeattr')
        if not checkbox.is_selected():
            checkbox.click()

        self.driver.find_element(By.ID, "create-project-button").click()

        element = self.wait_until_visible('#project-created-notification')
        self.assertTrue(self.element_exists('#project-created-notification'),
                        'Project creation notification not shown')
        self.assertTrue(project_name in element.text,
                        "New project name not in new project notification")
        self.assertTrue(Project.objects.filter(name=project_name).count(),
                        "New project not found in database")

        # check release
        self.assertTrue(re.search(
            release,
            self.driver.find_element(By.XPATH,
                                     "//span[@id='project-release-title']"
                                     ).text),
                        'The project release is not defined')


