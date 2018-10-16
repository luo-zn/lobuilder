#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Created By: Zhennan.luo(Jenner)
"""
import os
import fixtures
import itertools
from lobuilder.tests import base
from lobuilder import exception
from lobuilder.image import build
from lobuilder.tests.fakes import FAKE_IMAGE, FAKE_IMAGE_CHILD


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

    def test_unsupported_base_type(self):
        for base_distro, install_type in itertools.product(
                ['ubuntu', 'debian'], ['rdo', 'rhos']):
            self.conf.set_override('base', base_distro)
            self.conf.set_override('install_type', install_type)
            self.assertRaises(exception.MismatchBaseTypeException,
                              build.Worker, self.conf)

    def test_build_rpm_setup(self):
        """checking the length of list of docker commands"""
        self.conf.set_override('rpm_setup_config', ["a.rpm", "b.repo"])
        wk = build.Worker(self.conf)
        self.assertEqual(2, len(wk.rpm_setup))

    def test_extend_docker_path(self):
        fake_extend_path = os.path.abspath(os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 'fakes'))
        self.conf.set_default("extend_docker_path", fake_extend_path)
        wk = build.Worker(self.conf)

        wk.setup_working_dir()
