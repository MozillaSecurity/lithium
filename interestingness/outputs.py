#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring,missing-return-doc,missing-return-type-doc
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function

import optparse  # pylint: disable=deprecated-module
import sys

from . import fileIngredients, timedRun


def parseOptions(arguments):
    parser = optparse.OptionParser()
    parser.disable_interspersed_args()
    parser.add_option("-t", "--timeout", type="int", action="store", dest="condTimeout",
                      default=120,
                      help="Optionally set the timeout. Defaults to 120 seconds.")
    parser.add_option("-r", "--regex", action="store_true", dest="useRegex",
                      default=False,
                      help="Allow search for regular expressions instead of strings.")
    options, args = parser.parse_args(arguments)

    return options.condTimeout, options.useRegex, args


def interesting(cliArgs, tempPrefix):
    (timeout, regexEnabled, args) = parseOptions(cliArgs)

    searchFor = args[0]
    if not isinstance(searchFor, bytes):
        searchFor = searchFor.encode(sys.getfilesystemencoding())

    runinfo = timedRun.timed_run(args[1:], timeout, tempPrefix)

    result = (
        fileIngredients.fileContains(tempPrefix + "-out.txt", searchFor, regexEnabled)[0] or
        fileIngredients.fileContains(tempPrefix + "-err.txt", searchFor, regexEnabled)[0]
    )

    print("Exit status: %s (%.3f seconds)" % (runinfo.msg, runinfo.elapsedtime))

    return result
