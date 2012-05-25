#!/usr/bin/env python

from __future__ import with_statement

import os
import platform
import signal
import subprocess
import sys
import time

path0 = os.path.dirname(os.path.abspath(__file__))
path1 = os.path.abspath(os.path.join(path0, os.pardir, 'util'))
sys.path.append(path1)
from subprocesses import grabCrashLog

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
        try:
            p.kill()
        except WindowsError:
            if p.poll() == 0:
                # Verify that the process is really killed.
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
            assert False, 'We should no longer hit this since Python 2.6.5 is on MozillaBuild 1.5.1, already released for 1 year.'
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
        childStdOut = open(logPrefix + "-out", 'w')
        childStdErr = open(logPrefix + "-err", 'w')

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
                if progname == 'gdb':
                    raise Exception('Do not use this with gdb, because xpkill in timedRun will ' + \
                                    'kill gdb but leave the process within gdb still running')
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
        crashinfo = grabCrashLog(progname, commandWithArgs[0], child.pid, logPrefix)

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
