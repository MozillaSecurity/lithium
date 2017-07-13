#!/usr/bin/env python
# coding=utf-8
# flake8: noqa
# pylint: disable=missing-docstring

from __future__ import absolute_import

from setuptools import setup

if __name__ == "__main__":
    setup(name="lithium",
          version="0.1",
          entry_points={
              "console_scripts": ["lithium = lithium:main"]
          },
          packages=["lithium", "lithium.lithium"],
          package_data={"": [
              "interestingness/*",
              "lithium/doc/*",
              "lithium/examples/*.*",
              "lithium/examples/arithmetic/*"
          ]},
          package_dir={"lithium": ""},
          zip_safe=False)
