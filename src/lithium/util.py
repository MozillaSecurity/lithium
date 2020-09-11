# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Miscellaneous lithium utility functions"""

import logging

LOG = logging.getLogger(__name__)


class LithiumError(Exception):
    """Lithium error type."""


def summary_header():
    """Log a standard header for the lithium summary."""
    LOG.info("=== LITHIUM SUMMARY ===")


def divide_rounding_up(numerator, denominator):
    """Integer division, but always rounded up.

    Args:
        numerator (int): Input to divide.
        denominator (int): Amount to divide by.

    Returns:
        int: The result of the division, rounded up to the nearest integer.
    """
    quotient, remainder = divmod(numerator, denominator)
    return quotient + (1 if remainder else 0)


def is_power_of_two(inp):
    """Check whether or not the input is a power of two.

    Args:
        inp (int): Input.

    Returns:
        bool: True if the input is a power of two.
    """
    return (1 << max(inp.bit_length() - 1, 0)) == inp


def largest_power_of_two_smaller_than(inp):
    """Calculate the next smallest power of two.

    Args:
        inp (int): Input.

    Returns:
        int: The largest power of two that is smaller than the input.
    """
    result = 1 << max(inp.bit_length() - 1, 0)
    if result == inp and inp > 1:
        result >>= 1
    return result


def quantity(amount, unit):
    """Convert a quantity to a string, with correct pluralization.
    Formatting is delayed until str() since this is usually used for logging.

    Args:
        amount (int): Amount to represent
        unit (str): The units of the amount to print (eg. "iteration")

    Returns:
        object: A string-able object representing the amount with units,
                pluralized if necessary.
    """

    class _:
        def __str__(self):
            result = "%s %s" % (amount, unit)
            if amount != 1:
                result += "s"
            return result

    return _()
