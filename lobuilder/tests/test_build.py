#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Created By: Zhennan.luo(Jenner)
"""
import os
import mock
import fixtures
import itertools
from lobuilder.tests import base
from lobuilder import exception
from lobuilder.image import build
from lobuilder.tests.fakes import FAKE_IMAGE, FAKE_IMAGE_CHILD


class TasksTest(base.TestCase):
    def setUp(self):
        super(TasksTest, self).setUp()
        self.image = FAKE_IMAGE.copy()
        # NOTE(jeffrey4l): use a real, temporary dir
        self.image.path = self.useFixture(fixtures.TempDir()).path

    @mock.patch('docker.version', '2.7.0')
    @mock.patch.dict(os.environ, clear=True)
    @mock.patch('docker.Client')
    def test_push_image_before_v3_0_0(self, mock_client):
        pusher = build.PushTask(self.conf, self.image)
        pusher.run()
        mock_client().push.assert_called_once_with(
            self.image.canonical_name, stream=True, insecure_registry=True)

    @mock.patch('docker.version', '3.0.0')
    @mock.patch.dict(os.environ, clear=True)
    @mock.patch('docker.Client')
    def test_push_image(self, mock_client):
        pusher = build.PushTask(self.conf, self.image)
        pusher.run()
        mock_client().push.assert_called_once_with(
            self.image.canonical_name, stream=True)

    @mock.patch.dict(os.environ, clear=True)
    @mock.patch('docker.Client')
    def test_build_image(self, mock_client):
        push_queue = mock.Mock()
        builder = build.BuildTask(self.conf, self.image, push_queue)
        builder.run()

        mock_client().build.assert_called_once_with(
            path=self.image.path, tag=self.image.canonical_name,
            nocache=False, rm=True, pull=True, forcerm=True,
            buildargs=None)

        self.assertTrue(builder.success)


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
            os.path.dirname(os.path.realpath(__file__)), 'fakes', 'docker'))
        self.conf.set_default("extend_docker_path", fake_extend_path)
        wk = build.Worker(self.conf)
        wk.setup_working_dir()
        images_dir = os.listdir(wk.working_dir)
        for item in os.listdir(fake_extend_path):
            self.assertIn(item, images_dir)

    def test_build_image_list_adds_plugins(self):

        self.conf.set_override('install_type', 'source')

        wk = build.Worker(self.conf)
        wk.setup_working_dir()
        wk.find_dockerfiles()
        wk.create_dockerfiles()
        wk.build_image_list()
        expected_plugin = {
            'name': 'neutron-server-plugin-networking-arista',
            'reference': 'master',
            'source': 'https://git.openstack.org/openstack/networking-arista',
            'type': 'git'
        }
        found = False
        for image in wk.images:
            if image.name == 'neutron-server':
                for plugin in image.plugins:
                    if plugin == expected_plugin:
                        found = True
                        break
                break
        if not found:
            self.fail('Can not find the expected neutron arista plugin')

    def test_build_image_list_plugin_parsing(self):
        """Ensure regex used to parse plugins adds them to the correct image"""
        self.conf.set_override('install_type', 'source')

        wk = build.Worker(self.conf)
        wk.setup_working_dir()
        wk.find_dockerfiles()
        wk.create_dockerfiles()
        wk.build_image_list()
        for image in wk.images:
            if image.name == 'base':
                self.assertEqual(len(image.plugins), 0,
                                 'base image should not have any plugins '
                                 'registered')
                break
        else:
            self.fail('Expected to find the base image in this test')

    @mock.patch('pprint.pprint')
    def test_list_dependencies(self, pprint_mock):
        self.conf.set_override('profile', ['all'])
        wk = build.Worker(self.conf)
        wk.images = self.images
        wk.filter_images()
        wk.list_dependencies()
        pprint_mock.assert_called_once_with(mock.ANY)
