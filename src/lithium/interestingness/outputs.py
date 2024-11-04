# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lithium's "outputs" interestingness test to assess whether an intended message shows
up.

Example:
    python -m lithium outputs --timeout=9 FOO <binary> --fuzzing-safe <testcase>
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from . import utils
from .timed_run import BaseParser, timed_run

LOG = logging.getLogger(__name__)


def file_contains(path: Path | str, is_regex: bool, search: str) -> bool:
    """Determine if string is present in a file.

    Args:
        path:
        is_regex:
        search:

    Returns:

    """
    if is_regex:
        return utils.file_contains_regex(path, search.encode())[0]
    return utils.file_contains_str(path, search.encode())


def interesting(
    cli_args: list[str] | None = None,
    temp_prefix: str | None = None,
) -> bool:
    """Interesting if the binary causes an intended message to show up. (e.g. on
    stdout/stderr)

    Args:
        cli_args: List of input arguments.
        temp_prefix: Temporary directory prefix, e.g. tmp1/1 or tmp4/1

    Returns:
        True if the intended message shows up, False otherwise.
    """
    parser = BaseParser()
    parser.add_argument(
        "-s",
        "--search",
        help="String to search for.",
        required=True,
    )
    parser.add_argument(
        "-r",
        "--regex",
        action="store_true",
        default=False,
        help="Treat string as a regular expression",
    )
    args = parser.parse_args(cli_args)
    if not args.cmd_with_flags:
        parser.error("Must specify command to evaluate.")

    run_info = timed_run(args.cmd_with_flags, args.timeout, temp_prefix)

    if temp_prefix is None:
        encoded = args.search.encode("utf-8")
        match = encoded if args.regex else re.escape(encoded)
        for data in (run_info.out, run_info.err):
            if re.search(match, data, flags=re.MULTILINE):
                LOG.info("[Interesting] Match detected!")
                return True

        LOG.info("[Uninteresting] No match detected!")
        return False

    result = any(
        file_contains(f"{temp_prefix}{suffix}", args.regex, args.search)
        for suffix in ("-out.txt", "-err.txt")
    )
    if result:
        LOG.info("[Interesting] Match detected!")
        return True

    LOG.info("[Uninteresting] No match detected!")
    return False


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    sys.exit(interesting())
