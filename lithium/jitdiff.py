#!/usr/bin/env python

import os, sys, ntr

def interesting(args, tempPrefix):
    program = args[0]
    testcase = args[1]
    timeout = 10
    
    runinfo1 = ntr.timed_run([program, testcase], timeout, tempPrefix + "-r1")
    runinfo2 = ntr.timed_run([program, "-j", testcase], timeout, tempPrefix + "-r2")

    if runinfo1.sta == ntr.TIMED_OUT:
        print "TIMED OUT [without jit], assuming uninteresting"
        return False
    if runinfo2.sta == ntr.TIMED_OUT:
        print "TIMED OUT [with jit], assuming uninteresting"
        return False

    r1out = open(tempPrefix + "-r1-out").read()
    r2out = open(tempPrefix + "-r2-out").read()
    return r1out != r2out
