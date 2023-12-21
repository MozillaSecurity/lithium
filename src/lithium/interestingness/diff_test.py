# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lithium's "diff_test" interestingness test to assess whether a binary shows a
difference in output when different command line arguments are passed in. This can be
used to isolate and minimize differential behaviour test cases.

Example:
    python -m lithium diff_test \
      -a "--fuzzing-safe" \
      -b "--fuzzing-safe --wasm-always-baseline" \
      <binary> <testcase>
"""
import argparse
import filecmp
import logging
import sys
from typing import List, Optional, Union

from .timed_run import BaseParser, ExitStatus, timed_run

LOG = logging.getLogger(__name__)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse args

    Args:
        argv: List of input arguments.

    Returns:
        Parsed arguments
    """
    parser = BaseParser(
        prog="diff_test",
        usage="python -m lithium.interestingness.diff "
        "-a '--fuzzing-safe' -b='' binary testcase.js",
    )
    parser.add_argument(
        "-a",
        dest="a_args",
        help="Set of extra arguments given to first run.",
        required=True,
    )
    parser.add_argument(
        "-b",
        dest="b_args",
        help="Set of extra arguments given to second run.",
        required=True,
    )

    args = parser.parse_args(argv)
    if not args.cmd_with_flags:
        parser.error("Must specify command to evaluate.")

    return args


def interesting(
    cli_args: Optional[List[str]] = None,
    temp_prefix: Optional[str] = None,
) -> bool:
    """Check if there's a difference in output or return code with different args.

    Args:
        cli_args: Input arguments.
        temp_prefix: Temporary directory prefix, e.g. tmp1/1.

    Returns:
        True if a difference in output appears, False otherwise.
    """
    args = parse_args(cli_args)

    binary = args.cmd_with_flags[:1]
    testcase = args.cmd_with_flags[1:]

    # Run with arguments set A
    command_a = binary + args.a_args.split() + testcase
    log_prefix_a = f"{temp_prefix}-a" if temp_prefix else None
    a_run = timed_run(command_a, args.timeout, log_prefix_a)
    if a_run.status == ExitStatus.TIMEOUT:
        LOG.warning("Command A timed out!")

    # Run with arguments set B
    command_b = binary + args.b_args.split() + testcase
    log_prefix_b = f"{temp_prefix}-b" if temp_prefix else None
    b_run = timed_run(command_b, args.timeout, log_prefix_b)
    if b_run.status == ExitStatus.TIMEOUT:
        LOG.warning("Command B timed out!")

    # Compare return codes
    a_ret = a_run.return_code
    b_ret = b_run.return_code
    if a_ret != b_ret:
        LOG.info(f"[Interesting] Different return codes: {a_ret} vs {b_ret}")
        return True

    # Compare outputs
    def cmp_out(
        a_data: Union[str, bytes],
        b_run: Union[str, bytes],
        is_file: bool = False,
    ) -> bool:
        if is_file:
            return not filecmp.cmp(a_data, b_run)
        return a_data != b_run

    if temp_prefix:
        if cmp_out(a_run.out, b_run.out, True) or cmp_out(a_run.err, b_run.err, True):
            LOG.info("[Interesting] Differences in output detected")
            return True
    else:
        if cmp_out(a_run.out, b_run.out) or cmp_out(a_run.err, b_run.err):
            LOG.info("[Interesting] Differences in output detected")
            return True

    LOG.info("[Uninteresting] No differences detected")
    return False


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    sys.exit(interesting())
