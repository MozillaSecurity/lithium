#!/usr/bin/env python

import ntr

def filecontainsloud(f, s):
   found = False
   for line in file(f):
       if line.find(s) != -1:
           print line.rstrip()
           found = True
   return found

def interesting(args, tempPrefix):
    timeout = int(args[0])
    searchFor = args[1]
    
    runinfo = ntr.timed_run(args[2:], timeout, tempPrefix)

    print "(%.3f seconds)" % runinfo.elapsedtime

    return filecontainsloud(tempPrefix + "-out", searchFor) or \
           filecontainsloud(tempPrefix + "-err", searchFor)
