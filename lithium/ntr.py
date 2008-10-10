#!/usr/bin/env python -u

import os, signal, sys, time, platform, subprocess

exitBadUsage = 2

(CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE) = range(5)


def getSignalName(num):
    for p in dir(signal):
        if p.startswith("SIG") and not p.startswith("SIG_"):
            if getattr(signal, p) == num:
                return p
    return "Unknown signal"


def timed_run(commandWithArgs, timeout, logPrefix):
    if not isinstance(commandWithArgs, list):
        raise TypeError, "commandWithArgs should be a list (of strings)."
    if not isinstance(timeout, int):
        raise TypeError, "timeout should be an int."
    if not isinstance(logPrefix, str):
        raise TypeError, "logPrefix should be a string."

    commandWithArgs[0] = os.path.expanduser(commandWithArgs[0])
    
    progname = commandWithArgs[0].split("/")[-1]

    if progname == "firefox":
        # Running the |firefox| shell script makes our time-out kills useless,
        # prevents us from knowing the correct pid for crashes (needed on Leopard),
        # and screws with exit codes.
        print "I think you want firefox-bin!"
        sys.exit(exitBadUsage)
        
    starttime = time.time()
    
    sta = NONE
    msg = ''

    childStdOut = file(logPrefix + "-out", 'w')
    childStdErr = file(logPrefix + "-err", 'w')
    child = subprocess.Popen(commandWithArgs, stderr = childStdErr, stdout = childStdOut)

    killed = False

    while 1: 
        rc = child.poll()
        elapsedtime = time.time() - starttime
        if rc == None:
            if elapsedtime > timeout and not killed:
                # To be replaced with 'child.kill' when Python 2.6 is available,
                # since os.kill doesn't work on Windows.
                os.kill(child.pid, signal.SIGKILL)
                # but continue looping, because maybe kill takes a few seconds or maybe it's busy crashing!
                killed = True
            else:
                time.sleep(0.100)
        else:
            break
    
    # Am I supposed to do this?
    childStdOut.close()
    childStdErr.close()

    if rc == -signal.SIGKILL and killed:
        msg = 'TIMED OUT'
        sta = TIMED_OUT
    elif rc == 0:
        msg = 'NORMAL'
        sta = NORMAL
    elif rc > 0:
        msg = 'ABNORMAL return code ' + str(rc)
        sta = ABNORMAL
    else:
        # rc < 0
        # The program was terminated by a signal, which usually indicates a crash.
        # Mac/Linux only!
        signum = -rc
        msg = 'CRASHED signal %d (%s)' % (signum, getSignalName(signum))
        sta = CRASHED
        grabCrashLog(progname, child.pid, logPrefix, signum)

    return (sta, msg, elapsedtime)



def grabCrashLog(progname, crashedPID, logPrefix, signum):
    if os.path.exists(logPrefix + "-crash"):
        os.remove(logPrefix + "-crash")
    if os.path.exists(logPrefix + "-core"):
        os.remove(logPrefix + "-core")
    if platform.system() == "Darwin":
        found = False
        loops = 0
        while not found:
            if platform.mac_ver()[0].startswith("10.4"):
                # Tiger doesn't create crash logs for aborts.
                if signum == signal.SIGABRT:
                    #print "[grabCrashLog] No crash logs for aborts on Tiger."
                    break
                # On Tiger, the crash log file just grows and grows, and it's hard to tell
                # if the right crash is in there.  So sleep even if the file already exists.
                tigerCrashLogName = os.path.expanduser("~/Library/Logs/CrashReporter/" + progname + ".crash.log")
                time.sleep(2)
                if os.path.exists(tigerCrashLogName):
                    os.rename(tigerCrashLogName, logPrefix + "-crash")
                    found = True
            elif platform.mac_ver()[0].startswith("10.5"):
                # Look for a core file, in case the user did "ulimit -c unlimited"
                coreFilename = "/cores/core." + str(crashedPID)
                if os.path.exists(coreFilename):
                    os.rename(coreFilename, logPrefix + "-core")
                # Find a crash log for the right process name and pid, preferring
                # newer crash logs (which sort last).
                crashLogDir = os.path.expanduser("~/Library/Logs/CrashReporter/")
                crashLogs = os.listdir(crashLogDir)
                crashLogs = filter(lambda s: s.startswith(progname + "_"), crashLogs)
                crashLogs.sort(reverse=True)
                for fn in crashLogs:
                    fullfn = os.path.join(crashLogDir, fn)
                    try:
                        c = file(fullfn)
                        firstLine = c.readline()
                        c.close()
                        if firstLine.rstrip().endswith("[" + str(crashedPID) + "]"):
                            os.rename(fullfn, logPrefix + "-crash")
                            found = True
                            break
                    except IOError, e:
                        # Maybe the log was rotated out between when we got the list
                        # of files and when we tried to open this file.  If so, it's
                        # clearly not The One.
                        pass
            if not found:
                # print "[grabCrashLog] Waiting for the crash log to appear..."
                time.sleep(0.100)
                loops += 1
                if loops > 100:
                    # I suppose this might happen if the process corrupts itself so much that
                    # the crash reporter gets confused about the process name, for example.
                    print "[grabCrashLog] I waited a long time and the crash log never appeared!"
                    break



# Move the existing crash log out of the way (Tiger only)
# Not sure when to do this :(
#        if os.path.exists(tigerCrashLogName):
#            os.rename(tigerCrashLogName, "oldtigercrashlog")



