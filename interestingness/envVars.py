#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function

import copy
import os
import platform

isLinux = (platform.system() == 'Linux')
isMac = (platform.system() == 'Darwin')
isWin = (platform.system() == 'Windows')

ENV_PATH_SEPARATOR = ';' if os.name == 'nt' else ':'


def envWithPath(path, runningEnv=None):
    """Append the path to the appropriate library path on various platforms."""
    runningEnv = runningEnv or os.environ
    if isLinux:
        libPath = 'LD_LIBRARY_PATH'
    elif isMac:
        libPath = 'DYLD_LIBRARY_PATH'
    elif isWin:
        libPath = 'PATH'

    env = copy.deepcopy(runningEnv)
    if libPath in env:
        if path not in env[libPath]:
            env[libPath] += ENV_PATH_SEPARATOR + path
    else:
        env[libPath] = path

    return env


def findLlvmBinPath():
    """Return the path to compiled LLVM binaries, which differs depending on compilation method."""
    if isLinux:
        # Assumes clang was installed through apt-get. Works with version 3.6.2,
        # assumed to work with clang 3.8.0.
        # Create a symlink at /usr/bin/llvm-symbolizer for: /usr/bin/llvm-symbolizer-3.8
        if os.path.isfile('/usr/bin/llvm-symbolizer'):
            return ''

        print('WARNING: Please install clang via `apt-get install clang` if using Ubuntu.')
        print('then create a symlink at /usr/bin/llvm-symbolizer for: /usr/bin/llvm-symbolizer-3.8.')
        print('Try: `ln -s /usr/bin/llvm-symbolizer-3.8 /usr/bin/llvm-symbolizer`')
        return ''

    if isMac:
        # Assumes LLVM was installed through Homebrew. Works with at least version 3.6.2.
        brewLLVMPath = '/usr/local/opt/llvm/bin'
        if os.path.isdir(brewLLVMPath):
            return brewLLVMPath

        print('WARNING: Please install llvm from Homebrew via `brew install llvm`.')
        print('ASan stacks will not have symbols as Xcode does not install llvm-symbolizer.')
        return ''

    # https://developer.mozilla.org/en-US/docs/Building_Firefox_with_Address_Sanitizer#Manual_Build
    if isWin:
        return None  # The harness does not yet support Clang on Windows
