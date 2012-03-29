#!/usr/bin/env python

import os
import re
import sys
import timedRun

from optparse import OptionParser
path0 = os.path.dirname(__file__)
path1 = os.path.abspath(os.path.join(path0, os.pardir, 'util'))
sys.path.append(path1)
from fileIngredients import fileContains

def parseOptions(arguments):
    parser = OptionParser()
    parser.disable_interspersed_args()
    parser.add_option('-t', '--timeout', type='int', action='store', dest='condTimeout',
                      default = 120,
                      help='Optionally set the timeout. Defaults to 120 seconds.')
    parser.add_option('-r', '--regex', action='store_true', dest='useRegex',
                      default = False,
                      help = 'Allow search for regular expressions instead of strings.')
    options, args = parser.parse_args(arguments)

    return options.condTimeout, options.useRegex, args

def interesting(cliArgs, tempPrefix):
    (timeout, regexEnabled, args) = parseOptions(cliArgs)

    searchFor = args[0]

    runinfo = timedRun.timed_run(args[1:], timeout, tempPrefix)

    print "(%.3f seconds)" % runinfo.elapsedtime

    return fileContains(tempPrefix + "-out", searchFor, regexEnabled)[0] or \
           fileContains(tempPrefix + "-err", searchFor, regexEnabled)[0]
