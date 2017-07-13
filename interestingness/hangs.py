#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring

from __future__ import absolute_import, print_function

from . import timedRun


def interesting(args, tempPrefix):
    timeout = int(args[0])

    runinfo = timedRun.timed_run(args[1:], timeout, tempPrefix)

    if runinfo.sta == timedRun.TIMED_OUT:
        return True

    print("Exited in %.3f seconds" % runinfo.elapsedtime)
    return False
