#!/usr/bin/env python

import os, sys, ntr


def main():
    testcase = sys.argv[1]
    program = sys.argv[2]
    timeout = int(sys.argv[3])
    
    (sta, msg, elapsedtime) = ntr.timed_run([program, testcase], timeout, os.environ["LITHIUMTMP"])
    
    print "Exit status: %s (%.1f seconds)" % (msg, elapsedtime)

    if sta == ntr.CRASHED:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
