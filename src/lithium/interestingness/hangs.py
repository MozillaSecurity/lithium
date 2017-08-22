#!/usr/bin/env python
# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function

from . import timed_run


def interesting(args, tempPrefix):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    timeout = int(args[0])

    runinfo = timed_run.timed_run(args[1:], timeout, tempPrefix)

    if runinfo.sta == timed_run.TIMED_OUT:
        return True

    print("Exited in %.3f seconds" % runinfo.elapsedtime)
    return False
