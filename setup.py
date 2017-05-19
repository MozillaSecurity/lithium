#!/usr/bin/env python
from setuptools import setup

if __name__ == "__main__":
    setup(name = "lithium",
          version = "0.1",
          entry_points={
              "console_scripts": ["lithium = lithium:main"]
          },
          packages = ["lithium", "lithium.lithium"],
          package_data={"": [
              "interestingness/*",
              "lithium/doc/*",
              "lithium/examples/*",
              "lithium/examples/arithmetic/*"
          ]},
          package_dir = {"lithium": ""},
          zip_safe=False)
