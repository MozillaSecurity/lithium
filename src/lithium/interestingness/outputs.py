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

from lithium.interestingness import utils
from lithium.interestingness import timed_run


def parse_options(arguments):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
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


def interesting(cli_args, temp_prefix):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    (timeout, regex_enabled, args) = parse_options(cli_args)

    search_for = args[0]
    if not isinstance(search_for, bytes):
        search_for = search_for.encode(sys.getfilesystemencoding())

    runinfo = timed_run.timed_run(args[1:], timeout, temp_prefix)

    result = (
        utils.file_contains(temp_prefix + "-out.txt", search_for, regex_enabled)[0] or
        utils.file_contains(temp_prefix + "-err.txt", search_for, regex_enabled)[0]
    )

    print("Exit status: %s (%.3f seconds)" % (runinfo.msg, runinfo.elapsedtime))

    return result
