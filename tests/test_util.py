# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium utility tests"""

import logging
import math
import random
import sys

import pytest

import lithium

LOG = logging.getLogger(__name__)
pytestmark = pytest.mark.usefixtures("tmp_cwd")  # pylint: disable=invalid-name


def _ispow2(inp):
    """Simple version of `is_power_of_two` for testing and comparison

    Args:
        inp (int): input

    Returns:
        int: result
    """
    assert (
        isinstance(inp, int) or inp.is_integer()
    ), "ispow2() only works for integers, %r is not an integer" % (inp,)
    assert inp >= 1, "domain error"
    orig = inp
    result = True
    while inp > 1:
        if inp % 2:
            result = False
            break
        inp //= 2
    # if the input is representable as a float, compare the result to math library
    if orig <= sys.float_info.max:
        math_result = math.log(orig) / math.log(2)
        # diff to the next closest integer
        diff = abs(math_result - round(math_result))
        math_result = diff < 10 ** -(
            sys.float_info.dig - 1
        )  # float_info.dig is the # of decimal digits representable
        assert (
            result == math_result
        ), "ispow2(n) did not match math.log(n)/math.log(2) for n = %d" % (orig,)
    return result


def _divceil(num, den):
    """Simple version of `_divide_rounding_up` for testing and comparison

    Args:
        num (int): numerator
        den (int): denominator

    Returns:
        int: result
    """
    quo = num // den
    rem = num % den
    result = quo + (1 if rem else 0)
    # if the inputs are representable as a float, compare the result to math library
    if num <= sys.float_info.max and den <= sys.float_info.max:
        math_result = math.ceil(1.0 * num / den)
        assert (
            result == math_result
        ), "divceil(n,d) did not match math.ceil(n/d) for n = %d, d = %d" % (num, den)
    return result


def test_divide_rounding_up():
    """test `divide_rounding_up`"""
    for _ in range(10000):
        num = random.randint(1, (1 << 64) - 1)
        den = random.randint(1, num)
        try:
            assert _divceil(num, den) == lithium.util.divide_rounding_up(num, den)
            assert lithium.util.divide_rounding_up(num, num) == 1
            assert lithium.util.divide_rounding_up(0, num) == 0
            assert lithium.util.divide_rounding_up(num + 1, num) == 2
        except Exception:
            LOG.debug("n = %d, d = %d", num, den)
            raise


def test_is_power_of_two():
    """test `is_power_of_two`"""
    assert not lithium.util.is_power_of_two(0)
    # try all integers [1,10000)
    for i in range(1, 10000):
        try:
            assert _ispow2(i) == lithium.util.is_power_of_two(i)
        except Exception:
            LOG.debug("i = %d", i)
            raise
    # try 10000 random integers >= 10000
    for _ in range(10000):
        rand = random.randint(10000, (1 << 64) - 1)
        try:
            assert _ispow2(rand) == lithium.util.is_power_of_two(rand)
        except Exception:
            LOG.debug("inp = %d", rand)
            raise


def test_largest_power_of_two_smaller_than():
    """test `largest_power_of_two_smaller_than`"""
    assert lithium.util.largest_power_of_two_smaller_than(0) == 1

    def check_result(inp):
        result = lithium.util.largest_power_of_two_smaller_than(inp)
        # check that it is a power of two
        assert _ispow2(result)
        # check that it is < i
        if inp != 1:
            assert result < inp
        # check that the next power of 2 is >= i
        assert result * 2 >= inp

    # try all integers [1,10000)
    for inp in range(1, 10000):
        try:
            check_result(inp)
        except Exception:
            LOG.debug("inp = %d", inp)
            raise
    # try 10000 random integers >= 10000
    for _ in range(10000):
        rand = random.randint(10000, (1 << 64) - 1)
        try:
            check_result(rand)
        except Exception:
            LOG.debug("inp = %d", rand)
            raise
