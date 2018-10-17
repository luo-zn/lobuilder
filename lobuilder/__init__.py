#!/bin/env python
# -*- coding:utf-8 -*-

import threading

import pbr.version

__version__ = pbr.version.VersionInfo('lobuilder').version_string()

# Make a project global TLS trace storage repository
TLS = threading.local()
