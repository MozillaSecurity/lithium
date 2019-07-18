# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""This lets you import an interestingness test given a full path, or given just a filename.
(assuming it's in the current directory OR in the same directory as utils.py)
"""

from __future__ import print_function

import copy
import importlib
import logging
import os
import platform
import re
import sys


def env_with_path(path, curr_env=None):  # pylint: disable=missing-param-doc,missing-return-doc
    # pylint: disable=missing-return-type-doc,missing-type-doc
    """Append the path to the appropriate library path on various platforms."""
    curr_env = curr_env or os.environ
    if platform.system() == "Linux":
        lib_path = "LD_LIBRARY_PATH"
        path_sep = ":"
    elif platform.system() == "Darwin":
        lib_path = "DYLD_LIBRARY_PATH"
        path_sep = ":"
    elif platform.system() == "Windows":
        lib_path = "PATH"
        path_sep = ";"

    env = copy.deepcopy(curr_env)
    if lib_path in env:
        if path not in env[lib_path]:
            env[lib_path] += path_sep + path
    else:
        env[lib_path] = path

    return env


def file_contains(f, regex, is_regex, verbosity=True):  # pylint: disable=missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    if is_regex:
        return file_contains_regex(f, re.compile(regex, re.MULTILINE), verbose=verbosity)
    return file_contains_str(f, regex, verbose=verbosity), regex


def file_contains_str(file_, regex, verbose=True):  # pylint: disable=missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    with open(file_, "rb") as f:
        file_contents = f.read()
        idx = file_contents.find(regex)
        if idx != -1:
            if verbose and regex != b"":
                # rather than print the whole file, print the lines containing the match, up to the surrounding '\n'
                prev_nl = max(file_contents.rfind(b"\n", 0, idx + 1), 0)
                next_nl = idx + len(regex)
                if not regex.endswith(b"\n"):
                    next_nl = max(file_contents.find(b"\n", idx + len(regex)), next_nl)
                match = file_contents[prev_nl:next_nl].decode("utf-8", errors="replace")
                print("[Found string in: %r]" % (match,), end=" ")
            return True
    return False


def file_contains_regex(file_, regex, verbose=True):
    # pylint: disable=missing-param-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
    """e.g. python -m lithium crashesat --timeout=30
     --regex '^#0\\s*0x.* in\\s*.*(?:\\n|\\r\\n?)#1\\s*' ./js --fuzzing-safe --no-threads --ion-eager testcase.js
     Note that putting "^" and "$" together is unlikely to work."""

    matched_str = ""
    found = False
    with open(file_, "rb") as f:
        found_regex = regex.search(f.read())
        if found_regex:
            matched_str = found_regex.group()
            if verbose and matched_str != b"":
                print("[Found string in: '" + matched_str.decode("utf-8", errors="replace") + "']", end=" ")
            found = True
    return found, matched_str


def find_llvm_bin_path():  # pylint: disable=missing-return-doc,missing-return-type-doc,inconsistent-return-statements
    """Return the path to compiled LLVM binaries, which differs depending on compilation method."""
    if platform.system() == "Linux":
        # Assumes clang was installed through apt-get. Tested with LLVM 8
        # Create a symlink at /usr/bin/llvm-symbolizer for: /usr/bin/llvm-symbolizer-8
        linux_symbolizer_location = os.path.join(os.sep, "usr", "bin")
        if os.path.isfile(os.path.join(linux_symbolizer_location, "llvm-symbolizer")):
            return linux_symbolizer_location

        print("WARNING: Please install clang via `apt-get install clang` if using Ubuntu.")
        print("then create a symlink at /usr/bin/llvm-symbolizer for: /usr/bin/llvm-symbolizer-8")
        print("Try: `ln -s /usr/bin/llvm-symbolizer-8 /usr/bin/llvm-symbolizer`")
        return ""

    if platform.system() == "Darwin":
        # Assumes LLVM was installed through Homebrew. Works with at least version 3.6.2.
        mac_symbolizer_location = os.path.join(os.sep, "usr", "local", "opt", "llvm", "bin")
        if os.path.isfile(os.path.join(mac_symbolizer_location, "llvm-symbolizer")):
            return mac_symbolizer_location

        print("WARNING: Please install llvm from Homebrew via `brew install llvm`.")
        print("ASan stacks will not have symbols as Xcode does not install llvm-symbolizer.")
        return ""

    # https://developer.mozilla.org/en-US/docs/Building_Firefox_with_Address_Sanitizer#Manual_Build
    if platform.system() == "Windows":
        win_symbolizer_location = os.path.join(os.path.expanduser("~"), ".mozbuild", "clang", "bin")
        if os.path.isfile(os.path.join(win_symbolizer_location, "llvm-symbolizer.exe")):
            return win_symbolizer_location

        return None  # Cannot find llvm-symbolizer


def rel_or_abs_import(module):
    # pylint: disable=missing-param-doc,missing-raises-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
    """Import a module from anywhere.
    If a full path to module is given, try to import from there.
    If a relative path to module is given (module or module.py), try to import from current working
    directory or the lithium interestingness module.
    """
    log = logging.getLogger("lithium")

    orig_arg = module
    path, module = os.path.split(module)
    if not module:
        # module arg ended in slash, module must be a directory?
        path, module = os.path.split(path)
    if module.endswith(".py"):
        module = module[:-3]
    if path:
        # full path given, try that
        sys.path.append(os.path.realpath(path))
    else:
        sys.path.append(os.path.realpath("."))
    try:
        return importlib.import_module(module)
    except ImportError:
        # only raise if path was given, otherwise we also try under 'interestingness'
        if path:
            log.error("Failed to import: %s", orig_arg)
            log.error("From: %s", __file__)
            raise
    finally:
        sys.path.pop()
    # if we have not returned or raised by now, the import was unsuccessful and module was a name only
    # also try to import from 'interestingness'
    try:
        return importlib.import_module(".interestingness." + module, package="lithium")
    except ImportError:
        log.error("Failed to import: .interestingness.%s", module)
        log.error("From: %s", __file__)
        raise
