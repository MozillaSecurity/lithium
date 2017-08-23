#!/usr/bin/env python
# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import print_function

import copy
import os
import platform

ENV_PATH_SEPARATOR = ";" if os.name == "nt" else ":"


def env_with_path(path, curr_env=None):  # pylint: disable=missing-param-doc,missing-return-doc
    # pylint: disable=missing-return-type-doc,missing-type-doc
    """Append the path to the appropriate library path on various platforms."""
    curr_env = curr_env or os.environ
    if platform.system() == "Linux":
        lib_path = "LD_LIBRARY_PATH"
    elif platform.system() == "Darwin":
        lib_path = "DYLD_LIBRARY_PATH"
    elif platform.system() == "Windows":
        lib_path = "PATH"

    env = copy.deepcopy(curr_env)
    if lib_path in env:
        if path not in env[lib_path]:
            env[lib_path] += ENV_PATH_SEPARATOR + path
    else:
        env[lib_path] = path

    return env


def find_llvm_bin_path():  # pylint: disable=missing-return-doc,missing-return-type-doc
    """Return the path to compiled LLVM binaries, which differs depending on compilation method."""
    if platform.system() == "Linux":
        # Assumes clang was installed through apt-get. Works with version 3.6.2,
        # assumed to work with clang 3.8.0.
        # Create a symlink at /usr/bin/llvm-symbolizer for: /usr/bin/llvm-symbolizer-3.8
        if os.path.isfile("/usr/bin/llvm-symbolizer"):
            return ""

        print("WARNING: Please install clang via `apt-get install clang` if using Ubuntu.")
        print("then create a symlink at /usr/bin/llvm-symbolizer for: /usr/bin/llvm-symbolizer-3.8.")
        print("Try: `ln -s /usr/bin/llvm-symbolizer-3.8 /usr/bin/llvm-symbolizer`")
        return ""

    if platform.system() == "Darwin":
        # Assumes LLVM was installed through Homebrew. Works with at least version 3.6.2.
        brewLLVMPath = "/usr/local/opt/llvm/bin"  # pylint: disable=invalid-name
        if os.path.isdir(brewLLVMPath):
            return brewLLVMPath

        print("WARNING: Please install llvm from Homebrew via `brew install llvm`.")
        print("ASan stacks will not have symbols as Xcode does not install llvm-symbolizer.")
        return ""

    # https://developer.mozilla.org/en-US/docs/Building_Firefox_with_Address_Sanitizer#Manual_Build
    if platform.system() == "Windows":
        return None  # The harness does not yet support Clang on Windows
