#!/usr/bin/env python

import sys, ntr


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
    tries = int(sys.argv[3])
    searchFor = sys.argv[4]

    for i in range(tries):
        (sta, _, elapsedtime) = ntr.timed_run([program, testcase], 180, "t")
        print "(%.1f seconds)" % elapsedtime
        if filecontainsloud("t-out", searchFor) or filecontainsloud("t-err", searchFor):
            sys.exit(0)
        

if __name__ == "__main__":
    main()
    sys.exit(1)
