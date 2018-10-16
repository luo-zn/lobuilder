#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Created By: Zhennan.luo(Jenner)
"""
import os
import fixtures
from oslo_config import cfg
from oslotest import base as oslotest_base
from lobuilder.common import config as common_config

TESTS_ROOT = os.path.dirname(os.path.abspath(__file__))


class TestCase(oslotest_base.BaseTestCase):
    """All unit test should inherit from this class"""
    config_file = None

    def setUp(self):
        super(TestCase, self).setUp()
        self.conf = cfg.ConfigOpts()
        default_config_files = self.get_default_config_files()
        common_config.parse(self.conf, [],
                            default_config_files=default_config_files)
        # NOTE(jeffrey4l): mock the _get_image_dir method to return a fake
        # docker images dir
        self.useFixture(fixtures.MockPatch(
            'lobuilder.image.build.Worker._get_images_dir',
            mock.Mock(return_value=os.path.join(TESTS_ROOT, 'docker'))))

    def get_default_config_files(self):
        if self.config_file:
            return [os.path.join(TESTS_ROOT, 'etc', self.config_file)]
