#!/bin/env python
# -*- coding:utf-8 -*-
from __future__ import print_function

import datetime
import logging
import os
import sys
import shutil
import time
import tempfile
from oslo_config import cfg
from lobuilder import exception
from lobuilder.common import config as common_config


def make_a_logger(conf=None, image_name=None):
    if image_name:
        log = logging.getLogger(".".join([__name__, image_name]))
    else:
        log = logging.getLogger(__name__)
    if not log.handlers:
        if conf is None or not conf.logs_dir or not image_name:
            handler = logging.StreamHandler(sys.stdout)
            log.propagate = False
        else:
            filename = os.path.join(conf.logs_dir, "%s.log" % image_name)
            handler = logging.FileHandler(filename, delay=True)
        handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
        log.addHandler(handler)
    if conf is not None and conf.debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    return log


LOG = make_a_logger()

# Image status constants.
STATUS_CONNECTION_ERROR = 'connection_error'
STATUS_PUSH_ERROR = 'push_error'
STATUS_ERROR = 'error'
STATUS_PARENT_ERROR = 'parent_error'
STATUS_BUILT = 'built'
STATUS_BUILDING = 'building'
STATUS_UNMATCHED = 'unmatched'
STATUS_MATCHED = 'matched'
STATUS_UNPROCESSED = 'unprocessed'


class Image(object):
    def __init__(self, name, canonical_name, path, parent_name='',
                 status=STATUS_UNPROCESSED, parent=None,
                 source=None, logger=None):
        self.name = name
        self.canonical_name = canonical_name
        self.path = path
        self.status = status
        self.parent = parent
        self.source = source
        self.parent_name = parent_name
        if logger is None:
            logger = make_a_logger(image_name=name)
        self.logger = logger
        self.children = []
        self.plugins = []

    def copy(self):
        c = Image(self.name, self.canonical_name, self.path,
                  logger=self.logger, parent_name=self.parent_name,
                  status=self.status, parent=self.parent)
        if self.source:
            c.source = self.source.copy()
        if self.children:
            c.children = list(self.children)
        if self.plugins:
            c.plugins = list(self.plugins)
        return c

    def __repr__(self):
        return ("Image(%s, %s, %s, parent_name=%s,"
                " status=%s, parent=%s, source=%s)") % (
                   self.name, self.canonical_name, self.path,
                   self.parent_name, self.status, self.parent, self.source)


class Worker(object):
    def __init__(self, conf):
        self.conf = conf
        self.images_dir = self._get_images_dir()

        self.registry = conf.registry
        if self.registry:
            self.namespace = self.registry + '/' + conf.namespace
        else:
            self.namespace = conf.namespace

        self.base = conf.base
        self.base_tag = conf.base_tag
        self.install_type = conf.install_type
        self.tag = conf.tag
        self.images = list()
        rpm_setup_config = ([repo_file for repo_file in
                             conf.rpm_setup_config if repo_file is not None])
        self.rpm_setup = self.build_rpm_setup(rpm_setup_config)

        self._check_base_distribute()
        self._check_install_type()

        self.image_prefix = self.base + '-' + self.install_type + '-'

        self.regex = conf.regex
        self.image_statuses_bad = dict()
        self.image_statuses_good = dict()
        self.image_statuses_unmatched = dict()
        self.maintainer = conf.maintainer

    def _get_images_dir(self):
        possible_paths = (
            PROJECT_ROOT,
            os.path.join(sys.prefix, 'share/kolla'),
            os.path.join(sys.prefix, 'local/share/kolla'))

        for path in possible_paths:
            image_path = os.path.join(path, 'docker')
            # NOTE(SamYaple): We explicty check for the base folder to ensure
            #                 this is the correct path
            # TODO(SamYaple): Improve this to make this safer
            if os.path.exists(os.path.join(image_path, 'base')):
                LOG.info('Found the docker image folder at %s', image_path)
                return image_path
        else:
            raise exception.DirNotFoundException('Image dir can not '
                                                 'be found')

    def _check_base_distribute(self):
        rh_base = ['centos', 'oraclelinux', 'rhel']
        rh_type = ['source', 'binary', 'rdo', 'rhos']
        deb_base = ['ubuntu', 'debian']
        deb_type = ['source', 'binary']
        if not ((self.base in rh_base and self.install_type in rh_type) or
                    (self.base in deb_base and self.install_type in deb_type)):
            raise exception.MismatchBaseTypeException(
                '{} is unavailable for {}'.format(self.install_type, self.base)
            )

    def _check_install_type(self):
        if self.install_type == 'binary':
            self.install_metatype = 'rdo'
        elif self.install_type == 'source':
            self.install_metatype = 'mixed'
        elif self.install_type == 'rdo':
            self.install_type = 'binary'
            self.install_metatype = 'rdo'
        elif self.install_type == 'rhos':
            self.install_type = 'binary'
            self.install_metatype = 'rhos'
        else:
            raise exception.UnknownBuildTypeException(
                'Unknown install type'
            )

    def build_rpm_setup(self, rpm_setup_config):
        """Generates a list of docker commands based on provided configuration.

        :param rpm_setup_config: A list of .rpm or .repo paths or URLs
        :return: A list of docker commands
        """
        rpm_setup = list()
        for config in rpm_setup_config:
            if config.endswith('.rpm'):
                # RPM files can be installed with yum from file path or url
                cmd = "RUN yum -y install {}".format(config)
            elif config.endswith('.repo'):
                if config.startswith('http'):
                    # Curl http://url/etc.repo to /etc/yum.repos.d/etc.repo
                    name = config.split('/')[-1]
                    cmd = "RUN curl -L {} -o /etc/yum.repos.d/{}".format(
                        config, name)
                else:
                    # Copy .repo file from filesystem
                    cmd = "COPY {} /etc/yum.repos.d/".format(config)
            else:
                raise exception.RpmSetupUnknownConfig(
                    'RPM setup must be provided as .rpm or .repo files.'
                    ' Attempted configuration was {}'.format(config)
                )
            rpm_setup.append(cmd)
        return rpm_setup

    def copy_apt_files(self):
        if self.conf.apt_sources_list:
            shutil.copyfile(
                self.conf.apt_sources_list,
                os.path.join(self.working_dir, "base", "sources.list")
            )

        if self.conf.apt_preferences:
            shutil.copyfile(
                self.conf.apt_preferences,
                os.path.join(self.working_dir, "base", "apt_preferences")
            )

    def extend_docker_path(self, working_dir):
        edp = self.conf.extend_docker_path
        if edp and os.path.exists(edp):
            for name in os.listdir(edp):
                image_dir = os.path.join(working_dir, name)
                if os.path.exists(image_dir):
                    shutil.rmtree(image_dir)
                shutil.copyfile(os.path.join(edp, name), working_dir)

    def setup_working_dir(self):
        """Creates a working directory for use while building"""
        ts = time.time()
        ts = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H-%M-%S_')
        self.temp_dir = tempfile.mkdtemp(prefix='lobuilder-' + ts)
        self.working_dir = os.path.join(self.temp_dir, 'docker')
        shutil.copytree(self.images_dir, self.working_dir)
        self.extend_docker_path(self.working_dir)
        self.copy_apt_files()
        LOG.debug('Created working dir: %s', self.working_dir)


def run_build():
    """Build container images.

    :return: A 3-tuple containing bad, good, and unmatched container image
    status dicts, or None if no images were built.
    """
    conf = cfg.ConfigOpts()
    common_config.parse(conf, sys.argv[1:], prog='lobuilder')

    if conf.debug:
        LOG.setLevel(logging.DEBUG)

    wk = Worker(conf)
    wk.setup_working_dir()
