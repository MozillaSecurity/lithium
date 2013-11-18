#!/usr/bin/env python

import os
import platform
import signal
import subprocess
import sys
import time
from copy import deepcopy

path0 = os.path.dirname(os.path.abspath(__file__))
path1 = os.path.abspath(os.path.join(path0, os.pardir, 'util'))
sys.path.append(path1)
from subprocesses import envWithPath, grabCrashLog, isARMv7l, normExpUserPath, vdump

exitBadUsage = 2

(CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE) = range(5)


def getSignalName(num, default=None):
    for p in dir(signal):
        if p.startswith("SIG") and not p.startswith("SIG_"):
            if getattr(signal, p) == num:
                return p
    return default

class rundata(object):
  def __init__(self, sta, rc, msg, elapsedtime, killed, crashinfo, pid, out, err):
    self.sta = sta
    self.rc = rc
    self.msg = msg
    self.elapsedtime = elapsedtime
    self.killed = killed
    self.crashinfo = crashinfo
    self.pid = pid
    self.out = out
    self.err = err


def xpkill(p):
    '''Based on mozilla-central/source/build/automation.py.in'''
    try:
        p.kill()
    except WindowsError:
        if p.poll() == 0:
            try:
                print 'Trying to kill the process the first time...'
                p.kill() # Verify that the process is really killed.
            except WindowsError:
                if p.poll() == 0:
                    print 'Trying to kill the process the second time...'
                    p.kill() # Re-verify that the process is really killed.


def timed_run(commandWithArgs, timeout, logPrefix, wantStack, input=None):
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
        # This block will be moot when bug 658850 is fixed, if it isn't already.
        print "I think you want firefox-bin!"
        sys.exit(exitBadUsage)

    starttime = time.time()

    if useLogFiles:
        childStdOut = open(logPrefix + "-out.txt", 'w')
        childStdErr = open(logPrefix + "-err.txt", 'w')

    currEnv = deepcopy(os.environ)
    currEnv = envWithPath(os.path.dirname(os.path.abspath(commandWithArgs[0])))

    # Ideally we should use LLVM_ROOT from buildOptions.py, but we do not feel like importing
    # an entire options object for a non-default use-case, so hard-coding it here.
    ASAN_LLVM_ROOT = os.path.expanduser(os.path.join('~', 'llvm'))
    ASAN_SYMBOLIZE_PATH_WITH_CMAKE = normExpUserPath(
        os.path.join(ASAN_LLVM_ROOT, 'build', 'bin', 'llvm-symbolizer'))
    ASAN_SYMBOLIZE_PATH_NO_CMAKE = normExpUserPath(
        os.path.join(ASAN_LLVM_ROOT, 'build', 'Release+Asserts', 'bin', 'llvm-symbolizer'))

    vdump('progname is: ' + progname)
    if '-asan-' in progname:  # This is likely only going to work with js shells through the harness
        if os.path.isfile(ASAN_SYMBOLIZE_PATH_WITH_CMAKE):
            currEnv['ASAN_SYMBOLIZER_PATH'] = ASAN_SYMBOLIZE_PATH_WITH_CMAKE
            vdump('ASAN_SYMBOLIZE_PATH_WITH_CMAKE is found at: ' + ASAN_SYMBOLIZE_PATH_WITH_CMAKE)
        elif os.path.isfile(ASAN_SYMBOLIZE_PATH_NO_CMAKE):
            currEnv['ASAN_SYMBOLIZER_PATH'] = ASAN_SYMBOLIZE_PATH_NO_CMAKE
            vdump('ASAN_SYMBOLIZE_PATH_NO_CMAKE is found at: ' + ASAN_SYMBOLIZE_PATH_NO_CMAKE)
        else:
            print 'WARNING: Not symbolizing - ASan symbolizer is neither at ' + \
                ASAN_SYMBOLIZE_PATH_WITH_CMAKE + ' nor at ' + ASAN_SYMBOLIZE_PATH_NO_CMAKE

    def ulimitSet():
        # Sets soft limit of corefile size to be 500 million bytes in child process,
        # after fork() but before exec(), only on POSIX platforms (Linux / Mac).
        # See http://stackoverflow.com/a/1689991
        if os.name == 'posix':
            import resource; resource.setrlimit(resource.RLIMIT_CORE, (500000000, -1))
        if isARMv7l:
            # Pandaboards only have 1GB RAM, so restrict this early in the harness
            import resource; resource.setrlimit(resource.RLIMIT_AS, (500000000, -1))

    try:
        child = subprocess.Popen(
            commandWithArgs,
            stdin = (None         if (input == None) else subprocess.PIPE),
            stderr = (childStdErr if useLogFiles else subprocess.PIPE),
            stdout = (childStdOut if useLogFiles else subprocess.PIPE),
            close_fds = (os.name == "posix"),  # close_fds should not be changed on Windows
            env = currEnv,
            preexec_fn = ulimitSet if os.name == 'posix' else None
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
        crashinfo = grabCrashLog(progname, commandWithArgs[0], child.pid, logPrefix, wantStack)

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
        child.pid,
        logPrefix + "-out.txt" if useLogFiles else child.stdout.read(),
        logPrefix + "-err.txt" if useLogFiles else child.stderr.read()
    )
