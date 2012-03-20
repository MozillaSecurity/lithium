#!/usr/bin/env python

import timedRun

def interesting(args, tempPrefix):
    timeout = int(args[0])
    runinfo = timedRun.timed_run(args[1:], timeout, tempPrefix)
    print "Exit status: %s (%.3f seconds)" % (runinfo.msg, runinfo.elapsedtime)
    return runinfo.sta == timedRun.CRASHED
