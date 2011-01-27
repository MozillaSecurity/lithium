#!/usr/bin/env python

import os, signal, sys, time, platform, subprocess
THIS_SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))

exitBadUsage = 2
close_fds = (os.name == "posix") # would be nice to use this everywhere, but it's broken on Windows (http://docs.python.org/library/subprocess.html)

(CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE) = range(5)


def getSignalName(num, default=None):
    for p in dir(signal):
        if p.startswith("SIG") and not p.startswith("SIG_"):
            if getattr(signal, p) == num:
                return p
    return default

class rundata(object):
  def __init__(self, sta, rc, msg, elapsedtime, killed, crashinfo, out, err):
    self.sta = sta
    self.rc = rc
    self.msg = msg
    self.elapsedtime = elapsedtime
    self.killed = killed
    self.crashinfo = crashinfo
    self.out = out
    self.err = err


def xpkill(p):
    '''Based on mozilla-central/source/build/automation.py.in'''
    if hasattr(p, "kill"): # only available in python 2.6+
        # UNTESTED
        p.kill()
    elif os.name == "nt": # Windows
        pidString = str(p.pid)
        if platform.release() == "2000":
            # Windows 2000 needs 'kill.exe' from the 
            #'Windows 2000 Resource Kit tools'. (See bug 475455.)
            try:
                subprocess.Popen(["kill", "-f", pidString]).wait()
            except:
                print("Missing 'kill' utility to kill process with pid=%s. Kill it manually!" % pidString)
        else:
            # Windows XP and later.
            subprocess.Popen(["taskkill", "/F", "/PID", pidString]).wait()
    else:
        os.kill(p.pid, signal.SIGKILL)
 

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
            stdin = (None         if (input == None) else subprocess.PIPE),
            stderr = (childStdErr if useLogFiles else subprocess.PIPE),
            stdout = (childStdOut if useLogFiles else subprocess.PIPE),
            close_fds = close_fds
        )
    except OSError, e:
        print "Tried to run:"
        print "  " + repr(commandWithArgs)
        print "but got this error:"
        print "  " + str(e)
        sys.exit(2)

    if input != None:
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
        msg = 'CRASHED signal %d (%s)' % (signum, getSignalName(signum, "Unknown signal"))
        sta = CRASHED
        crashinfo = grabCrashLog(progname, commandWithArgs[0], child.pid, logPrefix, signum)

    if useLogFiles:
        # Am I supposed to do this?
        childStdOut.close()
        childStdErr.close()

    return rundata(
        sta,
        rc,
        msg,
        elapsedtime,
        killed,
        crashinfo,
        logPrefix + "-out" if useLogFiles else child.stdout.read(),
        logPrefix + "-err" if useLogFiles else child.stderr.read()
    )


def grabCrashLog(progname, progfullname, crashedPID, logPrefix, signum):
    if progname == "valgrind":
        return
    useLogFiles = isinstance(logPrefix, str)
    if useLogFiles:
        if os.path.exists(logPrefix + "-crash"):
            os.remove(logPrefix + "-crash")
        if os.path.exists(logPrefix + "-core"):
            os.remove(logPrefix + "-core")

    # On Mac and Linux, look for a core file.
    # In addition to the one-time setup mentioned below for each OS,
    # use the bash command "ulimit -c unlimited" before each invocation.
    coreFilename = None
    if platform.system() == "Darwin":
        # Assuming you ran: mkdir -p /cores/
        coreFilename = "/cores/core." + str(crashedPID)
    elif platform.system() == "Linux":
        # Assuming you ran: echo 1 | sudo tee /proc/sys/kernel/core_uses_pid
        # (I want to require this because otherwise multi-threading jsfunfuzz would result in core file collisions.)
        coreFilename = "core." + str(crashedPID)
    if coreFilename and os.path.exists(coreFilename):
        # Run gdb and move the core file.
        # Tip: gdb gives more info for (debug with intact build dir > debug > opt with frame pointers > opt)
        gdbCommandFile = os.path.join(THIS_SCRIPT_DIRECTORY, "gdb-quick.txt")
        gdbArgs = ["gdb", "-n", "-batch", "-x", gdbCommandFile, progfullname, coreFilename]
        print " ".join(gdbArgs)
        child = subprocess.call(
            gdbArgs,
            stdin =  None,
            stderr = subprocess.STDOUT,
            stdout = file(logPrefix + "-crash", 'w') if useLogFiles else None,
            close_fds = close_fds
        )
        if useLogFiles:
            os.rename(coreFilename, logPrefix + "-core")
            return logPrefix + "-crash"
        else:
            print "I don't know what to do with a core file when logPrefix is null"

    # On Mac, look for a crash log generated by Mac OS X Crash Reporter
    if platform.system() == "Darwin":
        found = False
        loops = 0
        while not found:
            # Find a crash log for the right process name and pid, preferring
            # newer crash logs (which sort last).
            crashLogDir = "~/Library/Logs/CrashReporter/" if platform.mac_ver()[0].startswith("10.5") else "~/Library/Logs/DiagnosticReports/"
            crashLogDir = os.path.expanduser(crashLogDir)
            try:
                crashLogs = os.listdir(crashLogDir)
            except (OSError, IOError), e:
                # Maybe this is the first crash ever on this computer, and the directory doesn't exist yet.
                crashLogs = []
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

                except (OSError, IOError), e:
                    # Maybe the log was rotated out between when we got the list
                    # of files and when we tried to open this file.  If so, it's
                    # clearly not The One.
                    pass
            if not found:
                # print "[grabCrashLog] Waiting for the crash log to appear..."
                time.sleep(0.100)
                loops += 1
                if loops > 1000:
                    # I suppose this might happen if the process corrupts itself so much that
                    # the crash reporter gets confused about the process name, for example.
                    print "grabCrashLog waited a long time, but a crash log for " + progname + " [" + str(crashedPID) + "] never appeared!"
                    break
