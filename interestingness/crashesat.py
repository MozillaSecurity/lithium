#!/usr/bin/env python

import os
import re
import sys
import timedRun

from optparse import OptionParser
path0 = os.path.dirname(os.path.abspath(__file__))
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

    desiredCrashSignature = args[0]
    runinfo = timedRun.timed_run(args[1:], timeout, tempPrefix)

    timeString = " (%.3f seconds)" % runinfo.elapsedtime

    crashLogName = tempPrefix + "-crash"

    if runinfo.sta == timedRun.CRASHED:
        if os.path.exists(crashLogName):
            # When using this script, remember to escape characters, e.g. "\(" instead of "(" !
            found, foundSig = fileContains(crashLogName, desiredCrashSignature, regexEnabled)
            if found:
                print "[CrashesAt] It crashed in " + foundSig + " :)" + timeString
                return True
            else:
                print "[CrashesAt] It crashed somewhere else!" + timeString
                return False
        else:
            print "[CrashesAt] It appeared to crash, but no crash log was found?" + timeString
            return False
    else:
        print "[CrashesAt] It didn't crash." + timeString
        return False
