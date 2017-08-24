#!/usr/bin/env python
# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""This lets you import an interestingness test given a full path, or given just a filename.
(assuming it's in the current directory OR in the same directory as ximport)
"""

import importlib
import logging
import os
import sys


def ximport(module):
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
            log.error("Failed to import: " + orig_arg)
            log.error("From: " + __file__)
            raise
    finally:
        sys.path.pop()
    # if we have not returned or raised by now, the import was unsuccessful and module was a name only
    # also try to import from 'interestingness'
    try:
        return importlib.import_module(".interestingness." + module, package="lithium")
    except ImportError:
        log.error("Failed to import: .interestingness." + module)
        log.error("From: " + __file__)
        raise
