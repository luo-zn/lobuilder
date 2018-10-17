#!/bin/env python
# -*- coding:utf-8 -*-

import threading

import pbr.version


__version__ = pbr.version.VersionInfo('lobuilder').version_string()

# Make a project global TLS trace storage repository
TLS = threading.local()

import os
import sys
# NOTE(SamYaple): Update the search path to prefer PROJECT_ROOT as the source
#                 of packages to import if we are using local tools instead of
#                 pip installed
PROJECT_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
