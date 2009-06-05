#!/usr/bin/env python

import ntr

def interesting(args, tempPrefix):
    timeout = int(args[0])
    runinfo = ntr.timed_run(args[1:], timeout, tempPrefix)
    print "Exit status: %s (%.3f seconds)" % (runinfo.msg, runinfo.elapsedtime)
    return runinfo.sta == ntr.CRASHED
