# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Run a subprocess with timeout
"""

import argparse
import collections
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import BinaryIO, Callable, Dict, List, Optional, Union

(CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE) = range(5)


# Define struct that contains data from a process that has already ended.
RunData = collections.namedtuple(
    "RunData",
    "sta, return_code, msg, elapsedtime, killed, out, err, pid",
)


class ArgumentParser(argparse.ArgumentParser):
    """Argument parser with `timeout` and `cmd_with_args`"""

    def __init__(self, *args, **kwds) -> None:  # type: ignore
        super().__init__(*args, **kwds)
        self.add_argument(
            "-t",
            "--timeout",
            default=120,
            dest="timeout",
            type=int,
            help="Set the timeout. Defaults to '%(default)s' seconds.",
        )
        self.add_argument("cmd_with_flags", nargs=argparse.REMAINDER)


def get_signal_name(signum: int, default: str = "Unknown signal") -> str:
    """Stringify a signal number. The result will be something like "SIGSEGV",
    or from Python 3.8, "Segmentation fault".

    Args:
        signum: Signal number to lookup
        default: Default to return if signal isn't recognized.

    Returns:
        String description of the signal.
    """
    if sys.version_info[:2] >= (3, 8) and platform.system() != "Windows":
        return signal.strsignal(signum) or default
    for member in dir(signal):
        if member.startswith("SIG") and not member.startswith("SIG_"):
            if getattr(signal, member) == signum:
                return member
    return default


def timed_run(
    cmd_with_args: List[str],
    timeout: int,
    log_prefix: str = "",
    env: Optional[Dict[str, str]] = None,
    inp: str = "",
    preexec_fn: Optional[Callable[[], None]] = None,
) -> RunData:
    """If log_prefix is None, uses pipes instead of files for all output.

    Args:
        cmd_with_args: List of command and parameters to be executed
        timeout: Timeout for the command to be run, in seconds
        log_prefix: Prefix string of the log files
        env: Environment for the command to be executed in
        inp: stdin to be passed to the command
        preexec_fn: called in child process after fork, prior to exec

    Raises:
        TypeError: Raises if input parameters are not of the desired types
                   (e.g. cmd_with_args should be a list)
        OSError: Raises if timed_run is attempted to be used with gdb

    Returns:
        A rundata instance containing run information
    """
    if not isinstance(cmd_with_args, list):
        raise TypeError("cmd_with_args should be a list (of strings).")
    if not isinstance(timeout, int):
        raise TypeError("timeout should be an int.")
    if log_prefix is not None and not isinstance(log_prefix, str):
        raise TypeError("log_prefix should be a string.")
    if preexec_fn is not None and not hasattr(preexec_fn, "__call__"):
        raise TypeError("preexec_fn should be callable.")

    prog = Path(cmd_with_args[0]).expanduser()
    cmd_with_args[0] = str(prog)

    if prog.stem == "gdb":
        raise OSError(
            "Do not use this with gdb, because kill in timed_run will "
            "kill gdb but leave the process within gdb still running"
        )

    sta = NONE
    msg = ""

    child_stderr: Union[int, BinaryIO] = subprocess.PIPE
    child_stdout: Union[int, BinaryIO] = subprocess.PIPE
    if log_prefix is not None:
        # pylint: disable=consider-using-with
        child_stdout = open(log_prefix + "-out.txt", "wb")
        child_stderr = open(log_prefix + "-err.txt", "wb")

    start_time = time.time()
    # pylint: disable=consider-using-with,subprocess-popen-preexec-fn
    child = subprocess.Popen(
        cmd_with_args,
        env=env,
        stderr=child_stderr,
        stdout=child_stdout,
        preexec_fn=preexec_fn,
    )
    try:
        stdout, stderr = child.communicate(
            input=inp.encode("utf-8"),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        child.kill()
        stdout, stderr = child.communicate()
        sta = TIMED_OUT
    except Exception as exc:  # pylint: disable=broad-except
        print("Tried to run:")
        print("  %r" % cmd_with_args)
        print("but got this error:")
        print("  %s" % exc)
        sys.exit(2)
    finally:
        if log_prefix is not None:
            child_stdout.close()
            child_stderr.close()
    elapsed_time = time.time() - start_time

    if sta == TIMED_OUT:
        msg = "TIMED OUT"
    elif child.returncode == 0:
        msg = "NORMAL"
        sta = NORMAL
    elif 0 < child.returncode < 0x80000000:
        msg = "ABNORMAL exit code " + str(child.returncode)
        sta = ABNORMAL
    else:
        # return_code < 0 (or > 0x80000000 in Windows)
        # The program was terminated by a signal, which usually indicates a crash.
        # Mac/Linux only!
        # XXX: this doesn't work on Windows
        if child.returncode < 0:
            signum = -child.returncode
        else:
            signum = child.returncode
        msg = "CRASHED signal %d (%s)" % (
            signum,
            get_signal_name(signum),
        )
        sta = CRASHED

    return RunData(
        sta,
        child.returncode if sta != TIMED_OUT else None,
        msg,
        elapsed_time,
        sta == TIMED_OUT,
        log_prefix + "-out.txt" if log_prefix is not None else stdout,
        log_prefix + "-err.txt" if log_prefix is not None else stderr,
        child.pid,
    )
