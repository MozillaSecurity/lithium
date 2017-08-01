#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring,missing-return-doc,missing-return-type-doc
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import print_function

import re


def fileContains(f, s, isRegex, vb=True):
    if isRegex:
        return fileContainsRegex(f, re.compile(s, re.MULTILINE), verbose=vb)
    return fileContainsStr(f, s, verbose=vb), s


def fileContainsStr(f, s, verbose=True):
    with open(f, "rb") as g:
        gContents = [l.strip() for l in g.read().splitlines() if l.strip()]
        for line in gContents:
            if line.find(s) != -1:
                if verbose and s != "":
                    print("[Found string in: '" + line.rstrip() + "']", end=" ")
                return True
    return False


def fileContainsRegex(f, regex, verbose=True):
    # e.g. ~/fuzzing/lithium/lithium.py crashesat --timeout=30
    #       --regex '^#0\s*0x.* in\s*.*(?:\n|\r\n?)#1\s*' ./js --ion -n 735957.js
    # Note that putting "^" and "$" together is unlikely to work.
    matchedStr = ""
    found = False
    with open(f, "rb") as g:
        foundRegex = regex.search(g.read())
        if foundRegex:
            matchedStr = foundRegex.group()
            if verbose and matchedStr != "":
                print("[Found string in: '" + matchedStr + "']", end=" ")
            found = True
    return found, matchedStr
