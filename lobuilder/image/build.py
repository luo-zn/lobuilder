#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Author: Zhennan.luo(Jenner)
"""
from __future__ import print_function

import sys
import os
import logging
from oslo_config import cfg
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


def run_build():
    """Build container images.

    :return: A 3-tuple containing bad, good, and unmatched container image
    status dicts, or None if no images were built.
    """
    conf = cfg.ConfigOpts()
    common_config.parse(conf, sys.argv[1:], prog='lobuilder')

    if conf.debug:
        LOG.setLevel(logging.DEBUG)
