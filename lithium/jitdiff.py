#!/usr/bin/env python

import os, sys, ntr

def interesting(args, tempPrefix):
    program = args[0]
    testcase = args[1]
    timeout = 2
    
    runinfo1 = ntr.timed_run([program, testcase], timeout, None, input="")
    runinfo2 = ntr.timed_run([program, "-j", testcase], timeout, None, input="")

    if runinfo1.sta == ntr.TIMED_OUT:
        print "TIMED OUT [without jit], assuming uninteresting"
        return False
    if runinfo2.sta == ntr.TIMED_OUT:
        print "TIMED OUT [with jit], assuming uninteresting"
        return False

    return runinfo1.out != runinfo2.out
