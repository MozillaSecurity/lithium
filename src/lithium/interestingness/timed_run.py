# coding=utf-8
# pylint: disable=missing-docstring
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function

import os
import platform
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


def xpkill(proc):
    """Based on mozilla-central/source/build/automation.py.in .

    Args:
        proc (process): Process to be killed
    """
    try:
        proc.kill()
    except WindowsError:  # pylint: disable=undefined-variable
        if proc.poll() == 0:
            try:
                print("Trying to kill the process the first time...")
                proc.kill()  # Verify that the process is really killed.
            except WindowsError:  # pylint: disable=undefined-variable
                if proc.poll() == 0:
                    print("Trying to kill the process the second time...")
                    proc.kill()  # Re-verify that the process is really killed.


def make_env(bin_path, curr_env=None):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
    curr_env = curr_env or os.environ
    env = utils.env_with_path(os.path.abspath(os.path.dirname(bin_path)), curr_env=curr_env)

    env["ASAN_OPTIONS"] = "exitcode=" + str(ASAN_EXIT_CODE)
    if platform.system() == "Linux":
        env["ASAN_OPTIONS"] = "detect_leaks=1," + env["ASAN_OPTIONS"]
        env["LSAN_OPTIONS"] = "max_leaks=1,"
    symbolizer_path = utils.find_llvm_bin_path()
    if symbolizer_path is not None:
        symbolizer_name = "llvm-symbolizer"
        if platform.system() == "Windows":
            symbolizer_name += ".exe"
        env["ASAN_SYMBOLIZER_PATH"] = os.path.join(symbolizer_path, symbolizer_name)
    return env


def timed_run(cmd_with_args, timeout, log_prefix, env=None, inp=None, preexec_fn=None):
    # pylint: disable=too-complex,too-many-arguments,too-many-branches,too-many-locals,too-many-statements
    """If log_prefix is None, uses pipes instead of files for all output.

    Args:
        cmd_with_args (list): List of command and parameters to be executed
        timeout (int): Timeout for the command to be run, in seconds
        log_prefix (str): Prefix string of the log files
        env (dict): Environment for the commmand to be executed in
        inp (str): stdin to be passed to the command
        preexec_fn (function): preexec_fn to be passed to subprocess.Popen

    Raises:
        TypeError: Raises if input parameters are not of the desired types (e.g. cmd_with_args should be a list)
        OSError: Raises if timed_run is attempted to be used with gdb

    Returns:
        class: A rundata instance containing run information
    """
    if not isinstance(cmd_with_args, list):
        raise TypeError("cmd_with_args should be a list (of strings).")
    if not isinstance(timeout, int):
        raise TypeError("timeout should be an int.")

    use_logfiles = isinstance(log_prefix, str)

    cmd_with_args[0] = os.path.expanduser(cmd_with_args[0])
    progname = cmd_with_args[0].split(os.path.sep)[-1]

    starttime = time.time()

    if use_logfiles:
        child_stdout = open(log_prefix + "-out.txt", "w")
        child_stderr = open(log_prefix + "-err.txt", "w")

    try:
        child = subprocess.Popen(
            cmd_with_args,
            stdin=(None if (inp is None) else subprocess.PIPE),
            stderr=(child_stderr if use_logfiles else subprocess.PIPE),
            stdout=(child_stdout if use_logfiles else subprocess.PIPE),
            close_fds=(os.name == "posix"),  # close_fds should not be changed on Windows
            env=(env or make_env(cmd_with_args[0], os.environ)),
            preexec_fn=preexec_fn
        )
    except OSError as ex:
        print("Tried to run:")
        print("  %r" % cmd_with_args)
        print("but got this error:")
        print("  %s" % ex)
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
                    raise OSError("Do not use this with gdb, because xpkill in timed_run will "
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

    if use_logfiles:
        # Am I supposed to do this?
        child_stdout.close()
        child_stderr.close()

    return rundata(
        sta,
        return_code,
        msg,
        elapsedtime,
        killed,
        child.pid,
        log_prefix + "-out.txt" if use_logfiles else child.stdout.read(),
        log_prefix + "-err.txt" if use_logfiles else child.stderr.read()
    )
