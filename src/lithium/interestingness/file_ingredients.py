#!/usr/bin/env python
# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import print_function

import re


def file_contains(f, regex, is_regex, verbosity=True):  # pylint: disable=missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    if is_regex:
        return file_contains_regex(f, re.compile(regex, re.MULTILINE), verbose=verbosity)
    return file_contains_str(f, regex, verbose=verbosity), regex


def file_contains_str(file_, regex, verbose=True):  # pylint: disable=missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    with open(file_, "rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.find(regex) != -1:
                if verbose and regex != b"":
                    print("[Found string in: '" + line.decode("utf-8", errors="replace") + "']", end=" ")
                return True
    return False


def file_contains_regex(file_, regex, verbose=True):
    # pylint: disable=missing-param-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
    """e.g. ~/fuzzing/lithium/lithium.py crashesat --timeout=30
     --regex '^#0\\s*0x.* in\\s*.*(?:\\n|\\r\\n?)#1\\s*' ./js --ion -n 735957.js
     Note that putting "^" and "$" together is unlikely to work."""

    matched_str = ""
    found = False
    with open(file_, "rb") as f:
        found_regex = regex.search(f.read())
        if found_regex:
            matched_str = found_regex.group()
            if verbose and matched_str != b"":
                print("[Found string in: '" + matched_str.decode("utf-8", errors="replace") + "']", end=" ")
            found = True
    return found, matched_str
