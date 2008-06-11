#!/usr/bin/env python


import sys, os, platform, time
import ntr

def filecontains(f, s):
   for line in f:
       if line.find(s) != -1:
           return True
   return False


testcase = sys.argv[1]
program = sys.argv[2]
desiredCrashSignature = sys.argv[3]



tigerCrashLogName = ""

(sta, msg, elapsedtime) = ntr.timed_run([program, testcase], 120, "t")

if sta == ntr.CRASHED:
    if os.path.exists("t-crash"):
        if filecontains(file("t-crash"), desiredCrashSignature):
            print "[CrashesAt] It crashed in " + desiredCrashSignature + " :)"
            sys.exit(0)
        else:
            print "[CrashesAt] It crashed somewhere else!"
            sys.exit(1)
    else:
        print "[CrashesAt] It appeared to crash, but no crash log was found?"
        sys.exit(1)
else:
    print "[CrashesAt] It didn't crash."
    sys.exit(1)
