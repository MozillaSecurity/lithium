# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lithium's "crashes" interestingness test to assess whether a binary crashes.

Example:
    python -m lithium crashes --timeout=9 <binary> --fuzzing-safe <testcase>
"""
from __future__ import annotations

import logging
import sys

from .timed_run import BaseParser, ExitStatus, timed_run

LOG = logging.getLogger(__name__)


def interesting(
    cli_args: list[str] | None = None,
    temp_prefix: str | None = None,
) -> bool:
    """Interesting if the binary causes a crash.

    Args:
        cli_args: List of input arguments.
        temp_prefix: Temporary directory prefix, e.g. tmp1/1 or tmp4/1

    Returns:
        True if binary crashes, False otherwise.
    """
    parser = BaseParser()
    args = parser.parse_args(cli_args)
    if not args.cmd_with_flags:
        parser.error("Must specify command to evaluate.")

    run_info = timed_run(args.cmd_with_flags, args.timeout, temp_prefix)

    if run_info.status == ExitStatus.CRASH:
        LOG.info(f"[Interesting] Crash detected ({run_info.elapsed:.3f}s)")
        return True

    LOG.info(f"[Uninteresting] No crash detected ({run_info.elapsed:.3f}s)")
    return False


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    sys.exit(interesting())
