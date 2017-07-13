#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring

'''
This test minimizes a test case by comparing a single binary with different command line arguments.
This can be used to isolate and minimize differential behaviour test cases.
'''

# This file came from nbp's GitHub PR #2 for adding new Lithium reduction strategies.
#   https://github.com/MozillaSecurity/lithium/pull/2

from __future__ import absolute_import, print_function

from optparse import OptionParser  # pylint: disable=deprecated-module

import filecmp
from . import timedRun


def parseOptions(arguments):
    parser = OptionParser()
    parser.disable_interspersed_args()
    parser.add_option('-t', '--timeout', type='int', action='store', dest='condTimeout',
                      default=120,
                      help='Optionally set the timeout. Defaults to "%default" seconds.')
    parser.add_option('-a', '--a-arg', type='string', action='append', dest='aArgs',
                      default=[],
                      help='Set of extra arguments given to first run.')
    parser.add_option('-b', '--b-arg', type='string', action='append', dest='bArgs',
                      default=[],
                      help='Set of extra arguments given to second run.')

    options, args = parser.parse_args(arguments)

    return options.condTimeout, options.aArgs, options.bArgs, args


def interesting(cliArgs, tempPrefix):
    (timeout, aArgs, bArgs, args) = parseOptions(cliArgs)

    aRuninfo = timedRun.timed_run(args[:1] + aArgs + args[1:], timeout, tempPrefix + "-a")
    bRuninfo = timedRun.timed_run(args[:1] + bArgs + args[1:], timeout, tempPrefix + "-b")
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
