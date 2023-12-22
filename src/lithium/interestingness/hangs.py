# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lithium's "hangs" interestingness test to assess whether a binary hangs.

Example:
    python -m lithium hangs --timeout=3 <binary> --fuzzing-safe <testcase>
"""

import logging
import sys
from typing import List, Optional

from .timed_run import BaseParser, ExitStatus, timed_run

LOG = logging.getLogger(__name__)


def interesting(
    cli_args: Optional[List[str]] = None,
    temp_prefix: Optional[str] = None,
) -> bool:
    """Interesting if the binary causes a hang.

    Args:
        cli_args: List of input arguments.
        temp_prefix: Temporary directory prefix, e.g. tmp1/1 or tmp4/1

    Returns:
        True if binary causes a hang, False otherwise.
    """
    parser = BaseParser()
    args = parser.parse_args(cli_args)
    if not args.cmd_with_flags:
        parser.error("Must specify command to evaluate.")

    run_info = timed_run(args.cmd_with_flags, args.timeout, temp_prefix)
    if run_info.status == ExitStatus.TIMEOUT:
        LOG.info(f"[Interesting] Timeout detected ({args.timeout:.3f}s)")
        return True

    LOG.info(f"[Uninteresting] Program exited ({run_info.elapsed:.3f}s)")
    return False


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    sys.exit(interesting())
