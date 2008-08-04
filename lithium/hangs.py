#!/usr/bin/env python

import os, sys, ntr


def main():
    testcase = sys.argv[1]
    program = sys.argv[2]
    timeout = int(sys.argv[3])
    
    (sta, _, elapsedtime) = ntr.timed_run([program, testcase], timeout, os.environ["LITHIUMTMP"])

    if sta == ntr.TIMED_OUT:
        sys.exit(0)
    else:
        print "Exited in %.1f seconds" % elapsedtime
        sys.exit(1)

if __name__ == "__main__":
    main()
