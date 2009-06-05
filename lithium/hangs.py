#!/usr/bin/env python

import ntr

def interesting(args, tempPrefix):
    timeout = int(args[0])
    
    runinfo = ntr.timed_run(args[1:], timeout, tempPrefix)

    if runinfo.sta == ntr.TIMED_OUT:
        return True
    else:
        print "Exited in %.3f seconds" % runinfo.elapsedtime
        return False
