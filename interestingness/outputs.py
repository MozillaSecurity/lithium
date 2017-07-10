#!/usr/bin/env python
# coding=utf-8

from __future__ import print_function

from optparse import OptionParser

import timedRun
import fileIngredients


def parseOptions(arguments):
    parser = OptionParser()
    parser.disable_interspersed_args()
    parser.add_option('-t', '--timeout', type='int', action='store', dest='condTimeout',
                      default=120,
                      help='Optionally set the timeout. Defaults to 120 seconds.')
    parser.add_option('-r', '--regex', action='store_true', dest='useRegex',
                      default=False,
                      help='Allow search for regular expressions instead of strings.')
    options, args = parser.parse_args(arguments)

    return options.condTimeout, options.useRegex, args


def interesting(cliArgs, tempPrefix):
    (timeout, regexEnabled, args) = parseOptions(cliArgs)

    searchFor = args[0]

    runinfo = timedRun.timed_run(args[1:], timeout, tempPrefix)

    result = (
        fileIngredients.fileContains(tempPrefix + "-out.txt", searchFor, regexEnabled)[0] or
        fileIngredients.fileContains(tempPrefix + "-err.txt", searchFor, regexEnabled)[0]
    )

    print("Exit status: %s (%.3f seconds)" % (runinfo.msg, runinfo.elapsedtime))

    return result
