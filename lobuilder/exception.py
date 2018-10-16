#!/bin/env python
# -*- coding:utf-8 -*-


class DirNotFoundException(Exception):
    pass


class RpmSetupUnknownConfig(Exception):
    pass


class MismatchBaseTypeException(Exception):
    pass


class UnknownBuildTypeException(Exception):
    pass
