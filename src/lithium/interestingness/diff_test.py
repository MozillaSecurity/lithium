# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lithium's "diff_test" interestingness test to assess whether a binary shows a difference in output when different
command line arguments are passed in. This can be used to isolate and minimize differential behaviour test cases.

Example:
    python -m lithium diff_test -a "--fuzzing-safe" -b "--fuzzing-safe --wasm-always-baseline" <binary> <testcase>

Example with autobisectjs, split into separate lines here for readability:
    python -u -m funfuzz.autobisectjs.autobisectjs -b "--enable-debug --enable-more-deterministic" -p testcase.js
      -i diff_test -a "--fuzzing-safe --no-threads --ion-eager"
                   -b "--fuzzing-safe --no-threads --ion-eager --no-wasm-baseline"
"""

# This file came from nbp's GitHub PR #2 for adding new Lithium reduction strategies.
#   https://github.com/MozillaSecurity/lithium/pull/2

from __future__ import absolute_import, print_function

import argparse
import filecmp
import logging

from . import timed_run


def interesting(cli_args, temp_prefix):
    """Interesting if the binary shows a difference in output when different command line arguments are passed in.

    Args:
        cli_args (list): List of input arguments.
        temp_prefix (str): Temporary directory prefix, e.g. tmp1/1 or tmp4/1

    Returns:
        bool: True if a difference in output appears, False otherwise.
    """
    parser = argparse.ArgumentParser(prog="diff_test",
                                     usage="python -m lithium %(prog)s [options] binary testcase.ext")
    parser.add_argument("-t", "--timeout", default=120, dest="timeout", type=int,
                        help="Set the timeout. Defaults to '%(default)s' seconds.")
    parser.add_argument("-a", "--a-args", dest="a_args", help="Set of extra arguments given to first run.")
    parser.add_argument("-b", "--b-args", dest="b_args", help="Set of extra arguments given to second run.")
    parser.add_argument("cmd_with_flags", nargs=argparse.REMAINDER)
    args = parser.parse_args(cli_args)

    a_runinfo = timed_run.timed_run(args.cmd_with_flags[:1] + args.a_args.split() + args.cmd_with_flags[1:],
                                    args.timeout,
                                    temp_prefix + "-a")
    b_runinfo = timed_run.timed_run(args.cmd_with_flags[:1] + args.b_args.split() + args.cmd_with_flags[1:],
                                    args.timeout,
                                    temp_prefix + "-b")
    log = logging.getLogger(__name__)
    time_str = "(1st Run: %.3f seconds) (2nd Run: %.3f seconds)" % (a_runinfo.elapsedtime, b_runinfo.elapsedtime)

    if a_runinfo.sta != timed_run.TIMED_OUT and b_runinfo.sta != timed_run.TIMED_OUT:
        if a_runinfo.return_code != b_runinfo.return_code:
            log.info("[Interesting] Different return code (%d, %d). %s",
                     a_runinfo.return_code, b_runinfo.return_code, time_str)
            return True
        if not filecmp.cmp(a_runinfo.out, b_runinfo.out):
            log.info("[Interesting] Different output. %s", time_str)
            return True
        if not filecmp.cmp(a_runinfo.err, b_runinfo.err):
            log.info("[Interesting] Different error output. %s", time_str)
            return True
    else:
        log.info("[Uninteresting] At least one test timed out. %s", time_str)
        return False

    log.info("[Uninteresting] Identical behaviour. %s", time_str)
    return False
