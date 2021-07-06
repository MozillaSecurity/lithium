# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""This tests Lithium's main "minimize" algorithm."""

import sys
from typing import List


def interesting(args: List[str], _temp_prefix: str) -> bool:
    """Interesting if the product of the numbers in the file divides the argument.

    Args:
        args: Input arguments.
        _temp_prefix: Temp directory prefix.

    Returns:
        True if successful, False otherwise.
    """
    mod = int(args[0])
    filename = args[1]

    prod = 1
    with open(filename, "r") as input_fp:
        for line in input_fp:
            line = line.strip()
            if line.isdigit():
                prod *= int(line)

    if prod % mod == 0:
        sys.stdout.write("%d is divisible by %d\n" % (prod, mod))
        return True

    sys.stdout.write("%d is not divisible by %d\n" % (prod, mod))
    return False
