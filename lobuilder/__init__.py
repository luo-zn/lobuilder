#!/bin/env python
# -*- coding:utf-8 -*-
"""
# Author: Zhennan.luo(Jenner)
"""

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
