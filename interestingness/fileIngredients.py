#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import print_function

import re


def fileContains(f, s, isRegex, vb=True):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    if isRegex:
        return fileContainsRegex(f, re.compile(s, re.MULTILINE), verbose=vb)
    return fileContainsStr(f, s, verbose=vb), s


def fileContainsStr(f, s, verbose=True):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    with open(f, "rb") as g:  # pylint: disable=invalid-name
        for line in g:
            line = line.strip()
            if not line:
                continue
            if line.find(s) != -1:
                if verbose and s != b"":
                    print("[Found string in: '" + line.decode("utf-8", errors="replace") + "']", end=" ")
                return True
    return False


def fileContainsRegex(f, regex, verbose=True):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    # e.g. ~/fuzzing/lithium/lithium.py crashesat --timeout=30
    #       --regex '^#0\s*0x.* in\s*.*(?:\n|\r\n?)#1\s*' ./js --ion -n 735957.js
    # Note that putting "^" and "$" together is unlikely to work.
    matchedStr = ""  # pylint: disable=invalid-name
    found = False
    with open(f, "rb") as g:  # pylint: disable=invalid-name
        foundRegex = regex.search(g.read())  # pylint: disable=invalid-name
        if foundRegex:
            matchedStr = foundRegex.group()  # pylint: disable=invalid-name
            if verbose and matchedStr != b"":
                print("[Found string in: '" + matchedStr.decode("utf-8", errors="replace") + "']", end=" ")
            found = True
    return found, matchedStr
