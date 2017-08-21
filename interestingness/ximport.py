#!/usr/bin/env python
# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""This lets you import an interestingness test given a full path, or given just a filename.
(assuming it's in the current directory OR in the same directory as ximport)
"""

import logging
import os
import sys

log = logging.getLogger("lithium")  # pylint: disable=invalid-name


def importRelativeOrAbsolute(f):  # pylint: disable=invalid-name
    # pylint: disable=missing-param-doc,missing-raises-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
    """Import an interestingness test given a full path or a filename."""

    # maybe there's a way to do this more sanely with the |imp| module...
    if f.endswith(".py"):
        f = f[:-3]
    if f.endswith(".pyc"):
        f = f[:-4]
    p, f = os.path.split(f)  # pylint: disable=invalid-name
    if p:
        # Add the path part of the given filename to the import path
        sys.path.append(p)
    else:
        # Add working directory to the import path
        sys.path.append(".")
    try:
        module = __import__(f)
    except ImportError as e:  # pylint: disable=invalid-name
        log.error("Failed to import: " + f)
        log.error("From: " + __file__)
        log.error(e)
        raise
    sys.path.pop()
    return module
