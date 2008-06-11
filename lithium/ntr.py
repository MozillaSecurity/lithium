#!/usr/bin/env python -u

import os, signal, sys, time


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
    else:
        msg = 'NONE'
        sta = NONE

    return (sta, msg, elapsedtime)
