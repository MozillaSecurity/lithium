#!/usr/bin/env python
# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""This test minimizes a test case by comparing a single binary with different command line arguments.
This can be used to isolate and minimize differential behaviour test cases.
"""

# This file came from nbp's GitHub PR #2 for adding new Lithium reduction strategies.
#   https://github.com/MozillaSecurity/lithium/pull/2

from __future__ import absolute_import, print_function

import filecmp
import optparse  # pylint: disable=deprecated-module

from . import timed_run


def parse_options(arguments):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    parser = optparse.OptionParser()
    parser.disable_interspersed_args()
    parser.add_option("-t", "--timeout", type="int", action="store", dest="condTimeout",
                      default=120,
                      help="Optionally set the timeout. Defaults to '%default' seconds.")
    parser.add_option("-a", "--a-arg", type="string", action="append", dest="aArgs",
                      default=[],
                      help="Set of extra arguments given to first run.")
    parser.add_option("-b", "--b-arg", type="string", action="append", dest="bArgs",
                      default=[],
                      help="Set of extra arguments given to second run.")

    options, args = parser.parse_args(arguments)

    return options.condTimeout, options.aArgs, options.bArgs, args


def interesting(cli_args, temp_prefix):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    (timeout, a_args, b_args, args) = parse_options(cli_args)

    a_runinfo = timed_run.timed_run(args[:1] + a_args + args[1:], timeout, temp_prefix + "-a")
    b_runinfo = timed_run.timed_run(args[:1] + b_args + args[1:], timeout, temp_prefix + "-b")
    time_str = " (1st Run: %.3f seconds) (2nd Run: %.3f seconds)" % (a_runinfo.elapsedtime, b_runinfo.elapsedtime)

    if a_runinfo.sta != timed_run.TIMED_OUT and b_runinfo.sta != timed_run.TIMED_OUT:
        if a_runinfo.return_code != b_runinfo.return_code:
            print("[Interesting] Different return code. (%d, %d)%s" %
                  (a_runinfo.return_code, b_runinfo.return_code, time_str))
            return True
        if not filecmp.cmp(a_runinfo.out, b_runinfo.out):
            print("[Interesting] Different output.%s" % time_str)
            return True
        if not filecmp.cmp(a_runinfo.err, b_runinfo.err):
            print("[Interesting] Different error output.%s" % time_str)
            return True
    else:
        print("[Uninteresting] At least one test timed out.%s" % time_str)
        return False

    print("[Uninteresting] Identical behaviour.%s" % time_str)
    return False
