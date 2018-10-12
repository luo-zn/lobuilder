#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Author: Zhennan.luo(Jenner)
"""
__author__ = "Jenner.luo"

from lobuilder import PROJECT_ROOT

from lobuilder.image import build


def main():
    statuses = build.run_build()
    if statuses:
        bad_results, good_results, unmatched_results = statuses
        if bad_results:
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())