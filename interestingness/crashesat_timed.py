#!/usr/bin/env python

import os
import timedRun

def filecontains(f, s):
   for line in f:
       if line.find(s) != -1:
           return True
   return False


def interesting(args, tempPrefix):
    timeout = int(args[0])
    desiredCrashSignature = args[1]

    runinfo = timedRun.timed_run(args[2:], timeout, tempPrefix)

    timeString = " (%.3f seconds)" % runinfo.elapsedtime

    crashLogName = tempPrefix + "-crash"

    if runinfo.sta == timedRun.CRASHED:
        if os.path.exists(crashLogName):
            if filecontains(file(crashLogName), desiredCrashSignature):
                print "[CrashesAt] It crashed in " + desiredCrashSignature + " :)" + timeString
                return True
            else:
                print "[CrashesAt] It crashed somewhere else!" + timeString
                return False
        else:
            print "[CrashesAt] It appeared to crash, but no crash log was found?" + timeString
            return False
    else:
        print "[CrashesAt] It didn't crash." + timeString
        return False
