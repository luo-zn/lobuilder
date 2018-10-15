#!/bin/env python
# -*- coding:utf-8 -*-
from __future__ import print_function

import os
import sys
import logging
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


class Worker(object):
    def __init__(self, conf):
        self.conf = conf
        self.images_dir = self._get_images_dir()

    def _get_images_dir(self):
        possible_paths = [
            PROJECT_ROOT,
            os.path.join(sys.prefix, 'share/lobuilder'),
            os.path.join(sys.prefix, 'local/share/lobuilder')]
        if self.conf.extend_path:
            possible_paths.index(0, self.conf.extend_path)


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
def run_build():
    """Build container images.

    :return: A 3-tuple containing bad, good, and unmatched container image
    status dicts, or None if no images were built.
    """
    conf = cfg.ConfigOpts()
    common_config.parse(conf, sys.argv[1:], prog='lobuilder')

    if conf.debug:
        LOG.setLevel(logging.DEBUG)
