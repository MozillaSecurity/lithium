#!/usr/bin/env python
# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function

import optparse  # pylint: disable=deprecated-module
import sys

from . import file_ingredients
from . import timed_run


def parseOptions(arguments):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
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


def interesting(cliArgs, tempPrefix):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    (timeout, regexEnabled, args) = parseOptions(cliArgs)  # pylint: disable=invalid-name

    searchFor = args[0]  # pylint: disable=invalid-name
    if not isinstance(searchFor, bytes):
        searchFor = searchFor.encode(sys.getfilesystemencoding())  # pylint: disable=invalid-name

    runinfo = timed_run.timed_run(args[1:], timeout, tempPrefix)

    result = (
        file_ingredients.fileContains(tempPrefix + "-out.txt", searchFor, regexEnabled)[0] or
        file_ingredients.fileContains(tempPrefix + "-err.txt", searchFor, regexEnabled)[0]
    )

    print("Exit status: %s (%.3f seconds)" % (runinfo.msg, runinfo.elapsedtime))

    return result
