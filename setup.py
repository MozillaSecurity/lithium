#!/usr/bin/env python
# coding=utf-8
# flake8: noqa
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

from setuptools import setup

if __name__ == "__main__":
    setup(name="lithium",
          version="0.1",
          entry_points={
              "console_scripts": ["lithium = lithium:main"]
          },
          packages=[
              "lithium",
              "lithium.lithium",
              "lithium.interestingness"
          ],
          package_data={"lithium": [
              "interestingness/*",
              "lithium/doc/*",
              "lithium/examples/*",
              "lithium/examples/arithmetic/*"
          ]},
          package_dir={"lithium": ""},
          zip_safe=False)
