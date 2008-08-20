#!/usr/bin/env python -u

import os, signal, sys, time, platform

exitBadUsage = 2
exitOSError   = 66
exitInterrupt = 99

(CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE) = range(5)

pid = None


def getSignalName(num):
    for p in dir(signal):
        if p.startswith("SIG") and not p.startswith("SIG_"):
            if getattr(signal, p) == num:
                return p
    return "Unknown signal"


def alarm_handler(signum, frame):
    global pid
    try:
        os.kill(pid, signal.SIGKILL)
    except:
        pass


def forkexec(commandWithArgs, logPrefix):
    newpid = os.fork()
    if newpid == 0: # Child

        try:
            # Redirect stdout, just for the child.
            so = file(logPrefix + "-out", 'w')
            os.dup2(so.fileno(), sys.stdout.fileno())

            # Redirect stderr, to a separate file.
            se = file(logPrefix + "-err", 'w')
            os.dup2(se.fileno(), sys.stderr.fileno())
            
            # Transfer control of the child to the target program
            # Its argv[0] wants to be the same as its path, so...
            os.execvp(commandWithArgs[0], commandWithArgs)
             
        except OSError, e:
            print "ERROR: %s failed: %d (%s)" % (repr(commandWithArgs), e.errno, e.strerror)
            # Note that we can only make the child process exit from here!
            # Use a special exit code (HACK!) to tell the parent to exit, too.
            sys.exit(exitOSError)

    else:  # Parent
        return newpid


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
        
        
    global pid
    global CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE
    
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(timeout)

    starttime = time.time()
    
    sta = NONE
    msg = ''

    pid = forkexec(commandWithArgs, logPrefix)

    try: 
      status = os.waitpid(pid, 0)[1]
    except OSError:
      # Guess that it timed out (waitpid throws "Interrupted system call" in this case!?)
      msg = 'TIMED OUT'
      sta = TIMED_OUT
    except KeyboardInterrupt:
      # Depending on how ntr.py was invoked, calling 'print' might throw an IOError, "Broken pipe"?!
      print "Bye!"
      try:
        os.kill(pid, signal.SIGKILL)
      except OSError, e:
        print "Unable to kill it: %s" % e
      sys.exit(exitInterrupt)
    
    signal.alarm(0) # Cancel the alarm

    stoptime = time.time()
    elapsedtime = stoptime - starttime
    
    if (sta == TIMED_OUT):
        pass
    elif os.WIFEXITED(status):
        rc = os.WEXITSTATUS(status)
        if rc == 0:
            msg = 'NORMAL'
            sta = NORMAL
        else:
            msg = 'ABNORMAL ' + str(rc)
            sta = ABNORMAL
    elif os.WIFSIGNALED(status):
        signum = os.WTERMSIG(status)
        msg = 'CRASHED signal %d (%s)' % (signum, getSignalName(signum))
        sta = CRASHED
        grabCrashLog(progname, pid, logPrefix + "-crash", signum)
    else:
        msg = 'NONE'
        sta = NONE

    return (sta, msg, elapsedtime)



def grabCrashLog(progname, crashedPID, newFilename, signum):
    if os.path.exists(newFilename):
        os.remove(newFilename)
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
                    os.rename(tigerCrashLogName, newFilename)
                    found = True
            elif platform.mac_ver()[0].startswith("10.5"):
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
                            os.rename(fullfn, newFilename)
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



