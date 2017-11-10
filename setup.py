#!/usr/bin/env python
# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from setuptools import setup

if __name__ == "__main__":
    setup(
        classifiers=[
            "Intended Audience :: Developers",
            "Topic :: Software Development :: Testing",
            "Topic :: Security",
            "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
            "Programming Language :: Python :: 2",
            "Programming Language :: Python :: 2.7",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.4",
            "Programming Language :: Python :: 3.5",
            "Programming Language :: Python :: 3.6"
        ],
        description="Lithium is an automated testcase reduction tool",
        entry_points={
            "console_scripts": ["lithium = lithium.reducer:main"]
        },
        keywords="fuzz fuzzing reduce reducer reduction security test testing",
        license="MPL 2.0",
        maintainer="Mozilla Fuzzing Team",
        maintainer_email="fuzzing@mozilla.com",
        name="lithium-reducer",
        package_data={"lithium": [
            "docs/*.*",
            "docs/examples/*.*",
            "docs/examples/arithmetic/*",
        ]},
        package_dir={"": "src"},
        packages=[
            "lithium",
            "lithium.interestingness",
        ],
        url="https://github.com/MozillaSecurity/lithium",
        version="0.2.1",
        zip_safe=False)
