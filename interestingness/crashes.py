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
from subprocesses import isWin

def parseOptions(arguments):
    parser = OptionParser()
    parser.disable_interspersed_args()
    parser.add_option('-r', '--regex', action='store_true', dest='useRegex',
                      default = False,
                      help = 'Allow search for regular expressions instead of strings.')
    parser.add_option('-s', '--sig', action='store', dest='sig',
                      default = '',
                      help='Optionally set the crash signature. Defaults to "%default".')
    parser.add_option('-t', '--timeout', type='int', action='store', dest='condTimeout',
                      default = 120,
                      help='Optionally set the timeout. Defaults to "%default" seconds.')

    options, args = parser.parse_args(arguments)

    return options.useRegex, options.sig, options.condTimeout, args

def interesting(cliArgs, tempPrefix):
    (regexEnabled, crashSig, timeout, args) = parseOptions(cliArgs)

    runinfo = timedRun.timed_run(args, timeout, tempPrefix)

    timeString = " (%.3f seconds)" % runinfo.elapsedtime

    crashLogName = tempPrefix + "-crash.txt"

    if runinfo.sta == timedRun.CRASHED:
        if isWin:
            # Our harness does not work with Windows core dumps. Yet, if in Windows, we enter
            # this function, we should have an interesting crash, so just go ahead and return.
            assert crashSig == '', 'The harness is not yet able to look for specific signatures' + \
                                    ' in Windows core dumps.'
            assert regexEnabled == False, 'The harness is not yet able to look for specific' + \
                                    ' regex signatures in Windows core dumps.'
            print 'Exit status: ' + runinfo.msg + timeString
            return True
        elif os.path.exists(crashLogName):
            # When using this script, remember to escape characters, e.g. "\(" instead of "(" !
            found, foundSig = fileContains(crashLogName, crashSig, regexEnabled)
            if found:
                print 'Exit status: ' + runinfo.msg + timeString
                return True
            else:
                print "[Uninteresting] It crashed somewhere else!" + timeString
                return False
        else:
            print "[Uninteresting] It appeared to crash, but no crash log was found?" + timeString
            return False
    else:
        print "[Uninteresting] It didn't crash." + timeString
        return False
