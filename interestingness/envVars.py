#!/usr/bin/env python
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import os
import platform
import subprocess
from multiprocessing import cpu_count

isLinux = (platform.system() == 'Linux')
isMac = (platform.system() == 'Darwin')
isWin = (platform.system() == 'Windows')

ENV_PATH_SEPARATOR = ';' if os.name == 'nt' else ':'


def normExpUserPath(p):
    return os.path.normpath(os.path.expanduser(p))

LLVM_ROOT = normExpUserPath(os.path.join('~', 'llvm'))
LLVM_BUILD_DIR = normExpUserPath(os.path.join(LLVM_ROOT, 'build'))


def cloneLLVMGit():
    '''Clones the Git mirror of LLVM.'''
    print 'Cloning git mirror of LLVM to compile clang...'
    subprocess.check_call(['git', 'clone', 'https://github.com/llvm-mirror/llvm.git'],
                          cwd=os.path.abspath(os.path.join(LLVM_ROOT, os.pardir)))
    # All 3 revisions are different because the SVN repo has 3 parts, so the git repos have 3 hashes.
    # SVN r214697 or git rev 534100b is assumed.
    subprocess.check_call(['git', 'checkout', '534100b31e1eba23effe750c1c996f594ea2e3b5'],
                          cwd=LLVM_ROOT)
    subprocess.check_call(['git', 'clone', 'https://github.com/llvm-mirror/clang.git'],
                          cwd=os.path.join(LLVM_ROOT, 'tools'))
    # SVN r214699 or git rev 5a85cc5 is assumed.
    subprocess.check_call(['git', 'checkout', '5a85cc570a8fb55f153afca689e905cdbfc93e7d'],
                          cwd=os.path.join(LLVM_ROOT, 'tools', 'clang'))
    subprocess.check_call(['git', 'clone', 'https://github.com/llvm-mirror/compiler-rt'],
                          cwd=os.path.join(LLVM_ROOT, 'projects'))
    # SVN r214604 or git rev 7e5e68a is assumed.
    subprocess.check_call(['git', 'checkout', '7e5e68aa23ebac22842938060ba4f308251f48f8'],
                          cwd=os.path.join(LLVM_ROOT, 'projects', 'compiler-rt'))
    print 'Finished cloning git mirror of LLVM.'


def compileLLVM():
    '''Compiles LLVM using cmake.'''
    print 'Running cmake...'
    cmakeCmdList = []
    if isLinux and float(platform.linux_distribution()[1]) > 15.04:
        # The revisions specified above fail to compile with GCC 5.2, which comes with Ubuntu 15.10 by default.
        cmakeCmdList += ['CC=/usr/bin/gcc-4.9', 'CXX=/usr/bin/g++-4.9']
    cmakeCmdList += ['cmake', '-DCMAKE_BUILD_TYPE:STRING=Release']
    if isMac:
        cmakeCmdList.append('-DLLVM_ENABLE_LIBCXX=ON')
    cmakeCmdList.append(LLVM_ROOT)
    subprocess.check_call(cmakeCmdList, cwd=LLVM_BUILD_DIR)
    print 'Running make...'
    subprocess.check_call(['make', '-s', '-j' + str(cpu_count())], cwd=LLVM_BUILD_DIR)
    print 'Finished compiling LLVM.'


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
    if isWin:
        return None  # The harness does not yet support Clang on Windows

    if not os.path.isdir(LLVM_ROOT) and not os.path.isdir(os.path.join(LLVM_ROOT, '.git')):
        cloneLLVMGit()
        try:
            os.mkdir(LLVM_BUILD_DIR)
        except OSError:
            raise Exception('Unable to create LLVM build folder.')
        compileLLVM()

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
