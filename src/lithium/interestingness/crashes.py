# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lithium's "crashes" interestingness test to assess whether a binary crashes.

Example:
    python -m lithium crashes --timeout=9 <binary> --fuzzing-safe <testcase>
"""

from __future__ import absolute_import

import argparse
import logging

from . import timed_run


def interesting(cli_args, temp_prefix):
    """Interesting if the binary causes a crash. (e.g. SIGKILL/SIGTERM/SIGTRAP etc.)

    Args:
        cli_args (list): List of input arguments.
        temp_prefix (str): Temporary directory prefix, e.g. tmp1/1 or tmp4/1

    Returns:
        bool: True if binary crashes, False otherwise.
    """
    parser = argparse.ArgumentParser(prog="crashes",
                                     usage="python -m lithium %(prog)s [options] binary [flags] testcase.ext")
    parser.add_argument("-t", "--timeout", default=120, dest="timeout", type=int,
                        help="Set the timeout. Defaults to '%(default)s' seconds.")
    parser.add_argument("cmd_with_flags", nargs=argparse.REMAINDER)
    args = parser.parse_args(cli_args)

    log = logging.getLogger(__name__)
    # Run the program with desired flags and look out for crashes.
    runinfo = timed_run.timed_run(args.cmd_with_flags, args.timeout, temp_prefix)

    time_str = " (%.3f seconds)" % runinfo.elapsedtime
    if runinfo.sta == timed_run.CRASHED:
        log.info("Exit status: " + runinfo.msg + time_str)
        return True

    log.info("[Uninteresting] It didn't crash: " + runinfo.msg + time_str)
    return False
