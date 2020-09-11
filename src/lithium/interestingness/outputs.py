# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium's "outputs" interestingness test to assess whether an intended message shows
up.

Example:
    python -m lithium outputs --timeout=9 FOO <binary> --fuzzing-safe <testcase>
"""

import logging
import os

from . import timed_run, utils


def interesting(cli_args, temp_prefix):
    """Interesting if the binary causes an intended message to show up. (e.g. on
    stdout/stderr)

    Args:
        cli_args (list): List of input arguments.
        temp_prefix (str): Temporary directory prefix, e.g. tmp1/1 or tmp4/1

    Returns:
        bool: True if the intended message shows up, False otherwise.
    """
    parser = timed_run.ArgumentParser(
        prog="outputs",
        usage="python -m lithium %(prog)s [options] output_message binary [flags] "
        "testcase.ext",
    )
    parser.add_argument(
        "-r",
        "--regex",
        action="store_true",
        default=False,
        help="Allow search for regular expressions instead of strings.",
    )
    args = parser.parse_args(cli_args)

    log = logging.getLogger(__name__)

    search_for = args.cmd_with_flags[0]
    if not isinstance(search_for, bytes):
        search_for = os.fsencode(search_for)

    # Run the program with desired flags and search stdout and stderr for intended
    # message
    runinfo = timed_run.timed_run(args.cmd_with_flags[1:], args.timeout, temp_prefix)

    def file_contains(path):
        if args.regex:
            return utils.file_contains_regex(path, search_for)[0]
        return utils.file_contains_str(path, search_for)

    result = any(
        file_contains(temp_prefix + suffix) for suffix in ("-out.txt", "-err.txt")
    )

    log.info("Exit status: %s (%.3f seconds)", runinfo.msg, runinfo.elapsedtime)
    return result
