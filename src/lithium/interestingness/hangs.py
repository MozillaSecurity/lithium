# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lithium's "hangs" interestingness test to assess whether a binary hangs.

Example:
    python -m lithium hangs --timeout=3 <binary> --fuzzing-safe <testcase>
"""

import logging
from typing import List

from . import timed_run


def interesting(cli_args: List[str], temp_prefix: str) -> bool:
    """Interesting if the binary causes a hang.

    Args:
        cli_args: List of input arguments.
        temp_prefix: Temporary directory prefix, e.g. tmp1/1 or tmp4/1

    Returns:
        True if binary causes a hang, False otherwise.
    """
    parser = timed_run.ArgumentParser(
        prog="hangs",
        usage="python -m lithium %(prog)s [options] binary [flags] testcase.ext",
    )
    args = parser.parse_args(cli_args)

    log = logging.getLogger(__name__)
    runinfo = timed_run.timed_run(args.cmd_with_flags, args.timeout, temp_prefix)

    if runinfo.sta == timed_run.TIMED_OUT:
        log.info("Timed out after %.3f seconds", args.timeout)
        return True

    log.info("Exited in %.3f seconds", runinfo.elapsedtime)
    return False
