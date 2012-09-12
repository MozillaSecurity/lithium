#!/usr/bin/env python

# Repeats an interestingness test a given number of times. To only loop the execution of the tests,
# RANGENUM is not needed. Add RANGENUM only if the testcase needs a variance of max loop iterations,
# such as a varying mjitChunkLimit depending on the m-c changeset.

# Use for:
# * Intermittent testcases.  If the testcase only triggers the bug 25% of the time, use |range 1 8|
# * Unstable testcases, where removing part of the testcase mysteriously requires changing a number
#   somewhere else in the testcase, e.g. needing to vary the number in mjitChunkLimit

# Example usage on m-c changeset 92fe907ddac8 with RANGENUM:
# $ python -u ~/fuzzing/lithium/lithium.py --strategy=check-only range 1 20 outputs --timeout=3 "enumerators" ./js-dbg-32-mozilla-central-linux -m -n -e "LOOPCOUNT=RANGENUM;" 740654.js
# $ python -u ~/fuzzing/lithium/lithium.py --strategy=check-only range 1 20 crashes 3 ./js-dbg-32-mozilla-central-linux -m -n -e "LOOPCOUNT=RANGENUM;" 740654.js
# (LOOPCOUNT is the upper limit of the for loop which wraps the testcase in bug 740654, note that
# this for loop has to be added manually. RANGENUM is defined in this file, see below)

# Example usage without RANGENUM:
# $ python -u ~/fuzzing/lithium/lithium.py --strategy=check-only range 1 20 outputs --timeout=3 "enumerators" ./js-dbg-32-mozilla-central-linux -m -n 740654.js
# $ python -u ~/fuzzing/lithium/lithium.py --strategy=check-only range 1 20 crashes 3 ./js-dbg-32-mozilla-central-linux -m -n 740654.js

import os
import sys
from optparse import OptionParser

import ximport
path0 = os.path.dirname(os.path.abspath(__file__))
path1 = os.path.abspath(os.path.join(path0, os.pardir, 'util'))
sys.path.append(path1)
from fileIngredients import fileContains

def parseOptions(arguments):
    parser = OptionParser()
    parser.disable_interspersed_args()
    options, args = parser.parse_args(arguments)

    return options, int(args[0]), int(args[1]), args[2:] # args[0] is minLoopNum, args[1] maxLoopNum

def interesting(cliArgs, tempPrefix):
    (options, rangeMin, rangeMax, arguments) = parseOptions(cliArgs)
    conditionScript = ximport.importRelativeOrAbsolute(arguments[0])
    conditionArgs = arguments[1:]

    assert (rangeMax - rangeMin) >= 0
    for i in xrange(rangeMin, rangeMax + 1):
        # This doesn't do anything if RANGENUM is not found.
        replacedConditionArgs = [s.replace('RANGENUM', str(i)) for s in conditionArgs]
        print 'Range number ' + str(i) + ':',
        if conditionScript.interesting(replacedConditionArgs, tempPrefix):
            return True

    return False
