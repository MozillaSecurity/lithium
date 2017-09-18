# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Repeats an interestingness test a given number of times. If "REPEATNUM" is present, it is replaced in turn with each
number as it increments. This "REPEATNUM" can be customized if required.

Use for:

1. Intermittent testcases.

   Repeating the test can make the bug occur often enough for Lithium to make progress.

    python -m lithium repeat 20 crashes --timeout=9 <binary> --fuzzing-safe <testcase>

2. Unstable testcases.

   Varying a number in the test (using REPEATNUM) may allow other parts of the testcase to be
   removed (Lithium), or may allow different versions of the shell to crash (autoBisect).

   In the testcase:
     schedulegc(n);

   On the command line: (SpiderMonkey-specific example)
     python -m lithium repeat 20 crashes --timeout=9 ./js --fuzzing-safe -e "n=REPEATNUM;" testcase.js
"""

from __future__ import absolute_import

import argparse
import logging

from .utils import rel_or_abs_import


def interesting(cli_args, temp_prefix):
    """Interesting if the desired interestingness test that is run together with "repeat" also reports "interesting".

    Args:
        cli_args (list): List of input arguments.
        temp_prefix (str): Temporary directory prefix, e.g. tmp1/1 or tmp4/1

    Returns:
        bool: True if the desired interestingness test also returns True, False otherwise.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--REPEATNUM", default="REPEATNUM", dest="repeat_num",
                        help="Set the cookie that is to be altered in the testcase. Defaults to '%(default)s'.")
    parser.add_argument("cmd_with_flags", nargs=argparse.REMAINDER)
    args = parser.parse_args(cli_args)

    log = logging.getLogger(__name__)

    loop_num = int(args.cmd_with_flags[0])
    assert loop_num > 0, "Minimum number of iterations should be at least 1"

    condition_script = rel_or_abs_import(args.cmd_with_flags[1])
    condition_args = args.cmd_with_flags[2:]

    if hasattr(condition_script, "init"):
        condition_script.init(condition_args)

    # Run the program over as many iterations as intended, with desired flags, replacing REPEATNUM where necessary.
    for i in range(1, loop_num + 1):
        # This doesn't do anything if REPEATNUM is not found.
        replaced_condition_args = [s.replace("REPEATNUM", str(i)) for s in condition_args]
        log.info("Repeat number %d:", i)
        if condition_script.interesting(replaced_condition_args, temp_prefix):
            return True

    return False
