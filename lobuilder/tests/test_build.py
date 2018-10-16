#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Created By: Zhennan.luo(Jenner)
"""
import fixtures
import itertools
from lobuilder.tests import base
from lobuilder.image import build

FAKE_IMAGE = build.Image(
    'image-base', 'image-base:latest',
    '/fake/path', parent_name=None,
    parent=None, status=build.STATUS_MATCHED)
FAKE_IMAGE_CHILD = build.Image(
    'image-child', 'image-child:latest',
    '/fake/path2', parent_name='image-base',
    parent=FAKE_IMAGE, status=build.STATUS_MATCHED)


class WorkerTest(base.TestCase):
    config_file = 'default.conf'

    def setUp(self):
        super(WorkerTest, self).setUp()
        image = FAKE_IMAGE.copy()
        image.status = None
        image_child = FAKE_IMAGE_CHILD.copy()
        image_child.status = None
        self.images = [image, image_child]

    def test_supported_base_type(self):
        rh_base = ['centos', 'oraclelinux', 'rhel']
        rh_type = ['source', 'binary', 'rdo', 'rhos']
        deb_base = ['ubuntu', 'debian']
        deb_type = ['source', 'binary']

        for base_distro, install_type in itertools.chain(
                itertools.product(rh_base, rh_type),
                itertools.product(deb_base, deb_type)):
            self.conf.set_override('base', base_distro)
            self.conf.set_override('install_type', install_type)
            # should no exception raised
            build.Worker(self.conf)
