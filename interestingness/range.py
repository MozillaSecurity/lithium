#!/usr/bin/env python
# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Repeats an interestingness test a given number of times.
If "RANGENUM" is present, it is replaced in turn with each number in the range.

Use for:

1. Intermittent testcases.

   Repeating the test can make the bug occur often enough for Lithium to make progress.

    lithium.py range 1 20 crashes --timeout=3 ./js-dbg-32-mozilla-central-linux -m -n intermittent.js

2. Unstable testcases.

   Varying a number in the test (using RANGENUM) may allow other parts of the testcase to be
   removed (Lithium), or may allow different versions of the shell to crash (autoBisect).

   In the testcase:
     schedulegc(n);

   On the command line:
     lithium.py range 1 50 crashes --timeout=3 ./js-dbg-32-mozilla-central-linux -e "n=RANGENUM;" 740654.js
"""

from __future__ import print_function

import optparse  # pylint: disable=deprecated-module
import os
import sys

path0 = os.path.dirname(os.path.abspath(__file__))  # pylint: disable=invalid-name
path1 = os.path.abspath(os.path.join(path0, os.pardir, 'util'))  # pylint: disable=invalid-name
sys.path.append(path1)
import ximport  # noqa  pylint: disable=relative-import,wrong-import-position


def parseOptions(arguments):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    parser = optparse.OptionParser()
    parser.disable_interspersed_args()
    _options, args = parser.parse_args(arguments)

    return int(args[0]), int(args[1]), args[2:]  # args[0] is minLoopNum, args[1] maxLoopNum


def interesting(cliArgs, tempPrefix):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    (rangeMin, rangeMax, arguments) = parseOptions(cliArgs)  # pylint: disable=invalid-name
    conditionScript = ximport.importRelativeOrAbsolute(arguments[0])  # pylint: disable=invalid-name
    conditionArgs = arguments[1:]  # pylint: disable=invalid-name

    if hasattr(conditionScript, "init"):
        conditionScript.init(conditionArgs)

    assert (rangeMax - rangeMin) >= 0
    for i in range(rangeMin, rangeMax + 1):
        # This doesn't do anything if RANGENUM is not found.
        replacedConditionArgs = [s.replace("RANGENUM", str(i)) for s in conditionArgs]  # pylint: disable=invalid-name
        print("Range number %d:" % i, end=" ")
        if conditionScript.interesting(replacedConditionArgs, tempPrefix):
            return True

    return False
