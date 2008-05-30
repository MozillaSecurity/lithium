#!/usr/bin/env python


import sys, os, platform, time
import ntr

exitBadUsage = 2



def grabCrashLog():
    if platform.system() == "Darwin":
        if platform.mac_ver()[0].startswith("10.4"):
            if os.path.exists("crash"):
                os.remove("crash")
            # Wait a little bit for the crash log to appear :(
            time.sleep(2)
            if os.path.exists(tigerCrashLogName):
                os.rename(tigerCrashLogName, "crash")
            else:
                print "Crash log is missing -- maybe it aborted instead of crashing, or I didn't wait long enough?"


def filecontains(f, s):
   for line in f:
       if line.find(s) != -1:
           return True
   return False


testcase = sys.argv[1]
program = sys.argv[2]
desiredCrashSignature = sys.argv[3]

progname = program.split("/")[-1]

if progname == "firefox":
    print "I think you want firefox-bin!"
    sys.exit(exitBadUsage)


tigerCrashLogName = ""

# Move the existing crash log out of the way (Tiger only)
if platform.system() == "Darwin":
    if platform.mac_ver()[0].startswith("10.4"):
        tigerCrashLogName = os.path.expanduser("~/Library/Logs/CrashReporter/" + progname + ".crash.log")
        if os.path.exists(tigerCrashLogName):
            os.rename(tigerCrashLogName, "oldcrashlog")



(sta, msg, elapsedtime) = ntr.timed_run([program, testcase], 120, "t")

if sta == ntr.CRASHED:
    grabCrashLog()
    if os.path.exists("crash"):
        if filecontains(file("crash"), desiredCrashSignature):
            print "CSAT: It crashed in " + desiredCrashSignature + " :)"
            sys.exit(0)
        else:
            print "CSAT: It crashed somewhere else."
            sys.exit(1)
    else:
        print "CSAT: It appeared to crash, but no crash log?"
        sys.exit(1)
else:
    print "CSAT: It didn't crash."
    sys.exit(1)
