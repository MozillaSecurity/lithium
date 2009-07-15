#!/usr/bin/env python

import os, signal, sys, time, platform, subprocess

exitBadUsage = 2

(CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE) = range(5)


def getSignalName(num):
    for p in dir(signal):
        if p.startswith("SIG") and not p.startswith("SIG_"):
            if getattr(signal, p) == num:
                return p
    return "Unknown signal"

class rundata(object):
  def __init__(self, sta, msg, elapsedtime, killed, crashinfo, out, err):
    self.sta = sta
    self.msg = msg
    self.elapsedtime = elapsedtime
    self.killed = killed
    self.crashinfo = crashinfo
    self.out = out
    self.err = err


def xpkill(p):
    if hasattr(p, "kill"): # only available in python 2.6+
        # UNTESTED
        p.kill()
    elif os.name == "posix": # not available on Windows
        os.kill(p.pid, signal.SIGKILL)
    else:
        # UNTESTED
        import win32process
        return win32process.TerminateProcess(process._handle, -1)


def timed_run(commandWithArgs, timeout, logPrefix, input=None):
    '''If logPrefix is None, uses pipes instead of files for all output.'''

    if not isinstance(commandWithArgs, list):
        raise TypeError, "commandWithArgs should be a list (of strings)."
    if not isinstance(timeout, int):
        raise TypeError, "timeout should be an int."

    useLogFiles = isinstance(logPrefix, str)

    commandWithArgs[0] = os.path.expanduser(commandWithArgs[0])
    progname = commandWithArgs[0].split(os.path.sep)[-1]

    if progname == "firefox" and os.name == "posix":
        # Running the |firefox| shell script makes our time-out kills useless,
        # prevents us from knowing the correct pid for crashes (needed on Leopard),
        # and screws with exit codes.
        print "I think you want firefox-bin!"
        sys.exit(exitBadUsage)
        
    starttime = time.time()
    
    if useLogFiles:
        childStdOut = file(logPrefix + "-out", 'w')
        childStdErr = file(logPrefix + "-err", 'w')

    try:
        child = subprocess.Popen(
            commandWithArgs,
            stdin = (None         if useLogFiles else subprocess.PIPE),
            stderr = (childStdErr if useLogFiles else subprocess.PIPE),
            stdout = (childStdOut if useLogFiles else subprocess.PIPE),
            close_fds = (os.name == "posix") # would be nice to use this everywhere, but it's broken on Windows (http://docs.python.org/library/subprocess.html)
        )
    except OSError, e:
        print "Tried to run:"
        print "  " + repr(commandWithArgs)
        print "but got this error:"
        print "  " + str(e)
        sys.exit(2)

    if not useLogFiles:
        child.stdin.write(input)
        child.stdin.close()

    sta = NONE
    msg = ''

    killed = False

    # It would be nice to have a timeout with less polling, but apparently that's hard
    # http://mail.python.org/pipermail/python-bugs-list/2009-April/075008.html
    # http://bugs.python.org/issue5673
    # http://benjamin.smedbergs.us/blog/2006-11-09/adventures-in-python-launching-subprocesses/
    # http://benjamin.smedbergs.us/blog/2006-12-11/killableprocesspy/

    # This part is a bit like subprocess.communicate, but with a timeout
    while 1:
        rc = child.poll()
        elapsedtime = time.time() - starttime
        if rc == None:
            if elapsedtime > timeout and not killed:
                xpkill(child)
                # but continue looping, because maybe kill takes a few seconds or maybe it's busy crashing!
                killed = True
            else:
                time.sleep(0.010)
        else:
            break
    
    crashinfo = None

    if killed and (os.name != "posix" or rc == -signal.SIGKILL):
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
        crashinfo = grabCrashLog(progname, child.pid, logPrefix, signum)

    if useLogFiles:
        # Am I supposed to do this?
        childStdOut.close()
        childStdErr.close()

    return rundata(
        sta,
        msg,
        elapsedtime,
        killed,
        crashinfo,
        logPrefix + "-out" if useLogFiles else child.stdout.read(),
        logPrefix + "-err" if useLogFiles else child.stderr.read()
    )


def grabCrashLog(progname, crashedPID, logPrefix, signum):
    useLogFiles = isinstance(logPrefix, str)
    if useLogFiles:
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
                if useLogFiles and os.path.exists(coreFilename):
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
                            if useLogFiles:
                                os.rename(fullfn, logPrefix + "-crash")
                                return logPrefix + "-crash"
                            else:
                                return fullfn
                                #return open(fullfn).read()

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



