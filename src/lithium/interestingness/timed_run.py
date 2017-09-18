# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function

import os
import signal
import subprocess
import sys
import time

from . import utils

ASAN_EXIT_CODE = 77

(CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE) = range(5)


def get_signal_name(num, default=None):  # pylint: disable=missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    for i in dir(signal):
        if i.startswith("SIG") and not i.startswith("SIG_"):
            if getattr(signal, i) == num:
                return i
    return default


class rundata(object):  # pylint: disable=invalid-name,missing-param-doc,missing-type-doc
    # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Define struct that contains data from a process that has already ended."""

    def __init__(self,  # pylint: disable=missing-param-doc,missing-type-doc,too-many-arguments
                 sta, return_code, msg, elapsedtime, killed, pid, out, err):
        """Initialize with given parameters."""
        self.sta = sta
        self.return_code = return_code
        self.msg = msg
        self.elapsedtime = elapsedtime
        self.killed = killed
        self.pid = pid
        self.out = out
        self.err = err


def xpkill(p):  # pylint: disable=invalid-name,missing-param-doc,missing-type-doc
    """Based on mozilla-central/source/build/automation.py.in ."""
    try:
        p.kill()
    except WindowsError:  # pylint: disable=undefined-variable
        if p.poll() == 0:
            try:
                print("Trying to kill the process the first time...")
                p.kill()  # Verify that the process is really killed.
            except WindowsError:  # pylint: disable=undefined-variable
                if p.poll() == 0:
                    print("Trying to kill the process the second time...")
                    p.kill()  # Re-verify that the process is really killed.


def make_env(bin_path):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    is_shell_deterministic = "-dm-" in bin_path
    # Total hack to make this not rely on queryBuildConfiguration in the funfuzz repository.
    # We need this so releng machines (which work off downloaded shells that are in build/dist/js),
    # do not compile LLVM.
    if not is_shell_deterministic:
        return None

    env = utils.env_with_path(os.path.abspath(os.path.dirname(bin_path)))
    env["ASAN_OPTIONS"] = "exitcode=" + str(ASAN_EXIT_CODE)
    symbolizer_path = utils.find_llvm_bin_path()
    if symbolizer_path is not None:
        env["ASAN_SYMBOLIZER_PATH"] = os.path.join(symbolizer_path, "llvm-symbolizer")
    return env


def timed_run(commandWithArgs, timeout, logPrefix, inp=None, preexec_fn=None):  # pylint: disable=invalid-name
    # pylint: disable=missing-param-doc,missing-raises-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
    # pylint: disable=too-complex,too-many-branches,too-many-locals,too-many-statements
    """If logPrefix is None, uses pipes instead of files for all output."""
    if not isinstance(commandWithArgs, list):
        raise TypeError("commandWithArgs should be a list (of strings).")
    if not isinstance(timeout, int):
        raise TypeError("timeout should be an int.")

    useLogFiles = isinstance(logPrefix, str)  # pylint: disable=invalid-name

    commandWithArgs[0] = os.path.expanduser(commandWithArgs[0])
    progname = commandWithArgs[0].split(os.path.sep)[-1]

    starttime = time.time()

    if useLogFiles:
        childStdOut = open(logPrefix + "-out.txt", "w")  # pylint: disable=invalid-name
        childStdErr = open(logPrefix + "-err.txt", "w")  # pylint: disable=invalid-name

    try:
        child = subprocess.Popen(
            commandWithArgs,
            stdin=(None if (inp is None) else subprocess.PIPE),
            stderr=(childStdErr if useLogFiles else subprocess.PIPE),
            stdout=(childStdOut if useLogFiles else subprocess.PIPE),
            close_fds=(os.name == "posix"),  # close_fds should not be changed on Windows
            env=make_env(commandWithArgs[0]),
            preexec_fn=preexec_fn
        )
    except OSError as e:  # pylint: disable=invalid-name
        print("Tried to run:")
        print("  %r" % commandWithArgs)
        print("but got this error:")
        print("  %s" % e)
        sys.exit(2)

    if inp is not None:
        child.stdin.write(inp)
        child.stdin.close()

    sta = NONE
    msg = ""

    killed = False

    # It would be nice to have a timeout with less polling, but apparently that's hard
    # http://mail.python.org/pipermail/python-bugs-list/2009-April/075008.html
    # http://bugs.python.org/issue5673
    # http://benjamin.smedbergs.us/blog/2006-11-09/adventures-in-python-launching-subprocesses/
    # http://benjamin.smedbergs.us/blog/2006-12-11/killableprocesspy/

    # This part is a bit like subprocess.communicate, but with a timeout
    while 1:
        return_code = child.poll()
        elapsedtime = time.time() - starttime
        if return_code is None:
            if elapsedtime > timeout and not killed:
                if progname == "gdb":
                    raise Exception("Do not use this with gdb, because xpkill in timed_run will "
                                    "kill gdb but leave the process within gdb still running")
                xpkill(child)
                # but continue looping, because maybe kill takes a few seconds or maybe it's busy crashing!
                killed = True
            else:
                time.sleep(0.010)
        else:
            break

    if killed and (os.name != "posix" or return_code == -signal.SIGKILL):  # pylint: disable=no-member
        msg = "TIMED OUT"
        sta = TIMED_OUT
    elif return_code == 0:
        msg = "NORMAL"
        sta = NORMAL
    elif return_code == ASAN_EXIT_CODE:
        msg = "CRASHED (Address Sanitizer fault)"
        sta = CRASHED
    elif 0 < return_code < 0x80000000:
        msg = "ABNORMAL exit code " + str(return_code)
        sta = ABNORMAL
    else:
        # return_code < 0 (or > 0x80000000 in Windows+py3)
        # The program was terminated by a signal, which usually indicates a crash.
        # Mac/Linux only!
        signum = -return_code
        msg = "CRASHED signal %d (%s)" % (signum, get_signal_name(signum, "Unknown signal"))
        sta = CRASHED

    if useLogFiles:
        # Am I supposed to do this?
        childStdOut.close()
        childStdErr.close()

    return rundata(
        sta,
        return_code,
        msg,
        elapsedtime,
        killed,
        child.pid,
        logPrefix + "-out.txt" if useLogFiles else child.stdout.read(),
        logPrefix + "-err.txt" if useLogFiles else child.stderr.read()
    )
