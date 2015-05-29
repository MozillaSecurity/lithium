#!/usr/bin/env python
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import os
import platform

isLinux = (platform.system() == 'Linux')
isMac = (platform.system() == 'Darwin')
isWin = (platform.system() == 'Windows')

ENV_PATH_SEPARATOR = ';' if os.name == 'nt' else ':'


def normExpUserPath(p):
    return os.path.normpath(os.path.expanduser(p))


def envWithPath(path, runningEnv=os.environ):
    '''Appends the path to the appropriate library path on various platforms.'''
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
    '''Returns the path to compiled LLVM binaries, which differs depending on compilation method.'''
    # https://developer.mozilla.org/en-US/docs/Building_Firefox_with_Address_Sanitizer#Manual_Build
    # FIXME: It would be friendlier to show instructions (or even offer to set up LLVM for the user,
    # with the right LLVM revision and build options). See MDN article on Firefox and Asan above.

    LLVM_ROOT = normExpUserPath(os.path.join('~', 'llvm'))

    LLVM_BUILD_DIR = normExpUserPath(os.path.join(LLVM_ROOT, 'build'))

    possibleBinPaths = [
        normExpUserPath(os.path.join(LLVM_BUILD_DIR, 'bin')),
        normExpUserPath(os.path.join(LLVM_BUILD_DIR, 'Release', 'bin')),
        normExpUserPath(os.path.join(LLVM_BUILD_DIR, 'Release+Asserts', 'bin'))
    ]

    for path in possibleBinPaths:
        if os.path.isdir(path):
            assert os.path.isfile(normExpUserPath(os.path.join(path, 'clang')))
            assert os.path.isfile(normExpUserPath(os.path.join(path, 'clang++')))
            assert os.path.isfile(normExpUserPath(os.path.join(path, 'llvm-symbolizer')))
            return path

    return None
