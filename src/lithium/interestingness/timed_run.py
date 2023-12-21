# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Run a subprocess with timeout"""
import argparse
import enum
import logging
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import BinaryIO, Callable, Dict, List, Optional, Union

from ffpuppet import SanitizerOptions

LOG = logging.getLogger(__name__)

ERROR_CODE = 77


class BaseParser(argparse.ArgumentParser):
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


class ExitStatus(enum.IntEnum):
    """Enum for recording exit status"""

    NORMAL = 1
    ABNORMAL = 2
    CRASH = 3
    TIMEOUT = 4


class RunData:
    """Class for storing run data"""

    def __init__(
        self,
        pid: int,
        status: ExitStatus,
        return_code: Union[int, None],
        message: str,
        elapsed: float,
        out: Union[bytes, str],
        err: Union[bytes, str],
    ):
        self.pid = pid
        self.status = status
        self.return_code = return_code
        self.message = message
        self.elapsed = elapsed
        self.out = out
        self.err = err


def _configure_sanitizers(orig_env: Dict[str, str]) -> Dict[str, str]:
    """Copy environment and update default values in *SAN_OPTIONS entries.

    Args:
        orig_env: Current environment.

    Returns:
        Environment with *SAN_OPTIONS defaults set.
    """
    env: Dict[str, str] = dict(orig_env)
    # https://github.com/google/sanitizers/wiki/SanitizerCommonFlags
    common_flags = [
        ("abort_on_error", "false"),
        ("allocator_may_return_null", "true"),
        ("disable_coredump", "true"),
        ("exitcode", str(ERROR_CODE)),  # use unique exitcode
        ("handle_abort", "true"),  # if true, abort_on_error=false to prevent hangs
        ("handle_sigbus", "true"),  # set to be safe
        ("handle_sigfpe", "true"),  # set to be safe
        ("handle_sigill", "true"),  # set to be safe
        ("symbolize", "true"),
    ]

    sanitizer_env_variables = (
        "ASAN_OPTIONS",
        "UBSAN_OPTIONS",
        "LSAN_OPTIONS",
        "TSAN_OPTIONS",
    )
    for sanitizer in sanitizer_env_variables:
        config = SanitizerOptions(env.get(sanitizer))
        for flag in common_flags:
            config.add(*flag)
        env[sanitizer] = str(config)

    return env


def _get_signal_name(signum: int, default: str = "Unknown signal") -> str:
    """Stringify a signal number

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
    log_prefix: Optional[str] = None,
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
        OSError: Raises if timed_run is attempted to be used with gdb

    Returns:
        A RunData instance containing run information.
    """
    if len(cmd_with_args) == 0:
        raise ValueError("Command not specified!")

    prog = Path(cmd_with_args[0]).resolve()

    if prog.stem == "gdb":
        raise OSError(
            "Do not use this with gdb, because kill in timed_run will "
            "kill gdb but leave the process within gdb still running"
        )

    status = None
    env = _configure_sanitizers(os.environ.copy() if env is None else env)
    child_stderr: Union[BinaryIO, int] = subprocess.PIPE
    child_stdout: Union[BinaryIO, int] = subprocess.PIPE
    if log_prefix is not None:
        # pylint: disable=consider-using-with
        child_stdout = open(f"{log_prefix}-out.txt", "wb")
        child_stderr = open(f"{log_prefix}-err.txt", "wb")

    start_time = time.time()
    # pylint: disable=consider-using-with,subprocess-popen-preexec-fn
    LOG.info(f"Running: {' '.join(cmd_with_args)}")
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
        status = ExitStatus.TIMEOUT
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error(exc)
        sys.exit(2)
    finally:
        if isinstance(child_stderr, BinaryIO) and isinstance(child_stdout, BinaryIO):
            child_stdout.close()
            child_stderr.close()
    elapsed_time = time.time() - start_time

    if status == ExitStatus.TIMEOUT:
        message = "TIMED OUT"
    elif child.returncode == 0:
        message = "NORMAL"
        status = ExitStatus.NORMAL
    elif child.returncode != ERROR_CODE and 0 < child.returncode < 0x80000000:
        message = f"ABNORMAL exit code {child.returncode}"
        status = ExitStatus.ABNORMAL
    else:
        # The program was terminated by a signal or by the sanitizer (ERROR_CODE)
        # Mac/Linux only!
        if child.returncode < 0:
            signum = abs(child.returncode)
            message = f"CRASHED with {_get_signal_name(signum)}"
        else:
            message = "CRASHED"

        status = ExitStatus.CRASH

    return RunData(
        child.pid,
        status,
        child.returncode if status != ExitStatus.TIMEOUT else None,
        message,
        elapsed_time,
        stdout if log_prefix is None else f"{log_prefix}-out.txt",
        stderr if log_prefix is None else f"{log_prefix}-err.txt",
    )
