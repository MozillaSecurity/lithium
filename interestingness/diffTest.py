#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""This test minimizes a test case by comparing a single binary with different command line arguments.
This can be used to isolate and minimize differential behaviour test cases.
"""

# This file came from nbp's GitHub PR #2 for adding new Lithium reduction strategies.
#   https://github.com/MozillaSecurity/lithium/pull/2

from __future__ import print_function

import filecmp
import optparse  # pylint: disable=deprecated-module

import timedRun  # pylint: disable=relative-import


def parseOptions(arguments):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
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


def interesting(cliArgs, tempPrefix):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    (timeout, aArgs, bArgs, args) = parseOptions(cliArgs)  # pylint: disable=invalid-name

    # pylint: disable=invalid-name
    aRuninfo = timedRun.timed_run(args[:1] + aArgs + args[1:], timeout, tempPrefix + "-a")
    # pylint: disable=invalid-name
    bRuninfo = timedRun.timed_run(args[:1] + bArgs + args[1:], timeout, tempPrefix + "-b")
    # pylint: disable=invalid-name
    timeString = " (1st Run: %.3f seconds) (2nd Run: %.3f seconds)" % (aRuninfo.elapsedtime, bRuninfo.elapsedtime)

    if aRuninfo.sta != timedRun.TIMED_OUT and bRuninfo.sta != timedRun.TIMED_OUT:
        if aRuninfo.rc != bRuninfo.rc:
            print("[Interesting] Different return code. (%d, %d)%s" % (aRuninfo.rc, bRuninfo.rc, timeString))
            return True
        if not filecmp.cmp(aRuninfo.out, bRuninfo.out):
            print("[Interesting] Different output.%s" % timeString)
            return True
        if not filecmp.cmp(aRuninfo.err, bRuninfo.err):
            print("[Interesting] Different error output.%s" % timeString)
            return True
    else:
        print("[Uninteresting] At least one test timed out.%s" % timeString)
        return False

    print("[Uninteresting] Identical behaviour.%s" % timeString)
    return False
