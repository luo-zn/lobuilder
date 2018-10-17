#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Created By: Zhennan.luo(Jenner)
"""
import abc
import os
import sys
import testtools
from mock import patch
from oslo_log import log as logging
from oslo_log import fixture as log_fixture
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../tools')))
from lobuilder.image import build
LOG = logging.getLogger(__name__)


class BuildTest(object):
    excluded_images = abc.abstractproperty()

    def setUp(self):
        super(BuildTest, self).setUp()
        self.useFixture(log_fixture.SetLogLevel([__name__],
                                                logging.logging.INFO))
        self.build_args = [__name__, "--debug", '--threads', '4']

    @testtools.skipUnless(os.environ.get('DOCKER_BUILD_TEST'),
                          'Skip the docker build test')
    def runTest(self):
        with patch.object(sys, 'argv', self.build_args):
            LOG.info("Running with args %s", self.build_args)
            bad_results, good_results, unmatched_results = build.run_build()

        failures = 0
        for image, result in bad_results.items():
            if image in self.excluded_images:
                if result is 'error':
                    continue
                failures = failures + 1
                LOG.warning(">>> Expected image '%s' to fail, please update"
                            " the excluded_images in source file above if the"
                            " image build has been fixed.", image)
            else:
                if result is not 'error':
                    continue
                failures = failures + 1
                LOG.critical(">>> Expected image '%s' to succeed!", image)

        for image in unmatched_results.keys():
            LOG.warning(">>> Image '%s' was not matched", image)

        self.assertEqual(failures, 0, "%d failure(s) occurred" % failures)
