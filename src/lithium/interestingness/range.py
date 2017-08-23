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

from __future__ import absolute_import, print_function

import optparse  # pylint: disable=deprecated-module

from . import ximport


def parse_options(arguments):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    parser = optparse.OptionParser()
    parser.disable_interspersed_args()
    _options, args = parser.parse_args(arguments)

    return int(args[0]), int(args[1]), args[2:]  # args[0] is minLoopNum, args[1] maxLoopNum


def interesting(cli_args, temp_prefix):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    (range_min, range_max, arguments) = parse_options(cli_args)
    condition_script = ximport.rel_or_abs_import(arguments[0])
    condition_args = arguments[1:]

    if hasattr(condition_script, "init"):
        condition_script.init(condition_args)

    assert (range_max - range_min) >= 0
    for i in range(range_min, range_max + 1):
        # This doesn't do anything if RANGENUM is not found.
        replaced_condition_args = [s.replace("RANGENUM", str(i)) for s in condition_args]
        print("Range number %d:" % i, end=" ")
        if condition_script.interesting(replaced_condition_args, temp_prefix):
            return True

    return False
