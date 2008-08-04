#!/usr/bin/env python

import os, sys, ntr


def filecontainsloud(f, s):
   found = False
   for line in file(f):
       if line.find(s) != -1:
           print line.rstrip()
           found = True
   return found


def main():
    testcase = sys.argv[1]
    program = sys.argv[2]
    timeout = int(sys.argv[3])
    searchFor = sys.argv[4]
    
    tmpPrefix = os.environ["LITHIUMTMP"]

    (sta, _, elapsedtime) = ntr.timed_run([program, testcase], timeout, tmpPrefix)

    #if sta == ntr.TIMED_OUT:
        #print "TIMED OUT"
        # But it doesn't really matter.

    print "(%.1f seconds)" % elapsedtime

    if filecontainsloud(tmpPrefix + "-out", searchFor) or \
       filecontainsloud(tmpPrefix + "-err", searchFor):
        sys.exit(0)
    else:
        sys.exit(1)
        

if __name__ == "__main__":
    main()
