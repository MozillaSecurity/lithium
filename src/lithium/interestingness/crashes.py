#!/usr/bin/env python
# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function

import optparse  # pylint: disable=deprecated-module

from . import timed_run


def parse_options(arguments):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    parser = optparse.OptionParser()
    parser.disable_interspersed_args()
    parser.add_option("-t", "--timeout", type="int", action="store", dest="condTimeout",
                      default=120,
                      help="Optionally set the timeout. Defaults to '%default' seconds.")

    options, args = parser.parse_args(arguments)

    return options.condTimeout, args


def interesting(cli_args, temp_prefix):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    (timeout, args) = parse_options(cli_args)

    runinfo = timed_run.timed_run(args, timeout, temp_prefix)
    time_str = " (%.3f seconds)" % runinfo.elapsedtime
    if runinfo.sta == timed_run.CRASHED:
        print("Exit status: " + runinfo.msg + time_str)
        return True

    print("[Uninteresting] It didn't crash: " + runinfo.msg + time_str)
    return False
