#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Author: Zhennan.luo(Jenner)
"""

import os
import sys
from lobuilder.image import build

# NOTE(SamYaple): Update the search path to prefer PROJECT_ROOT as the source
#                 of packages to import if we are using local tools instead of
#                 pip installed
PROJECT_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    statuses = build.run_build()
    if statuses:
        bad_results, good_results, unmatched_results = statuses
        if bad_results:
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

