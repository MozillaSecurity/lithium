#!/usr/bin/env python

import timedRun

def interesting(args, tempPrefix):
    timeout = int(args[0])

    wantStack = False  # No need to examine crash signatures here.
    runinfo = timedRun.timed_run(args[1:], timeout, tempPrefix, wantStack)

    if runinfo.sta == timedRun.TIMED_OUT:
        return True
    else:
        print "Exited in %.3f seconds" % runinfo.elapsedtime
        return False
