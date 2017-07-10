#!/usr/bin/env python
# coding=utf-8

from __future__ import print_function

import timedRun


def interesting(args, tempPrefix):
    timeout = int(args[0])

    runinfo = timedRun.timed_run(args[1:], timeout, tempPrefix)

    if runinfo.sta == timedRun.TIMED_OUT:
        return True
    else:
        print("Exited in %.3f seconds" % runinfo.elapsedtime)
        return False
