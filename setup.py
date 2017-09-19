#!/usr/bin/env python
# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from setuptools import setup

if __name__ == "__main__":
    setup(name="lithium",
          maintainer="Mozilla Fuzzing Team",
          maintainer_email="fuzzing@mozilla.com",
          url="https://github.com/MozillaSecurity/lithium",
          version="0.2.0",
          entry_points={
              "console_scripts": ["lithium = lithium.reducer:main"]
          },
          packages=[
              "lithium",
              "lithium.interestingness",
          ],
          package_data={"lithium": [
              "docs/*.*",
              "docs/examples/*.*",
              "docs/examples/arithmetic/*",
          ]},
          package_dir={"": "src"},
          zip_safe=False)
