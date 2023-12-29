# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium interestingness-test tests"""

import logging
import platform
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import lithium
from lithium.interestingness import outputs
from lithium.interestingness.timed_run import RunData

CAT_CMD = [
    sys.executable,
    "-c",
    (
        "import sys;"
        "[sys.stdout.buffer.write(f.read())"
        " for f in"
        "     ([open(a, 'rb') for a in sys.argv[1:]] or"
        "      [sys.stdin.buffer])"
        "]"
    ),
]
LS_CMD = [
    sys.executable,
    "-c",
    (
        "import glob,itertools,os,sys;"
        "[print(p)"
        " for p in"
        "     (itertools.chain.from_iterable(glob.glob(d) for d in sys.argv[1:])"
        "      if len(sys.argv) > 1"
        "      else os.listdir('.'))"
        "]"
    ),
]
SLEEP_CMD = [sys.executable, "-c", "import sys,time;time.sleep(int(sys.argv[1]))"]
LOG = logging.getLogger(__name__)
# pylint: disable=invalid-name
pytestmark = pytest.mark.usefixtures("tmp_cwd", "_tempjs")


@pytest.fixture
def _tempjs() -> None:
    with open("temp.js", "w"):
        pass


def _compile(in_path: Path, out_path: Path) -> None:
    """Try to compile a source file using any available C/C++ compiler.

    Args:
        in_path: Source file to compile from
        out_path: Executable file to compile to

    Raises:
        RuntimeError: Raises this exception if the compilation fails or if the compiler
                      cannot be found
    """
    if platform.system() == "Windows":
        compilers_to_try = ["cl", "clang", "gcc", "cc"]
    else:
        compilers_to_try = ["clang", "gcc", "cc"]

    assert Path(in_path).is_file()
    for compiler in compilers_to_try:
        out_param = "/Fe" if compiler == "cl" else "-o"
        try:
            out = subprocess.check_output(
                [compiler, out_param + str(out_path), str(in_path)],
                stderr=subprocess.STDOUT,
            )
        except OSError:
            LOG.debug("%s not found", compiler)
        except subprocess.CalledProcessError as exc:
            for line in exc.output.splitlines():
                LOG.debug("%s: %s", compiler, line.decode())
        else:
            for line in out.splitlines():
                LOG.debug("%s: %s", compiler, line.decode())
            return
    # all of compilers we tried have failed :(
    raise RuntimeError("Compile failed")


def test_crashes_0() -> None:
    """simple positive test for the 'crashes' interestingness test"""
    lith = lithium.Lithium()

    # check that `ls` doesn't crash
    result = lith.main(["--strategy", "check-only", "crashes"] + LS_CMD + ["temp.js"])
    assert result == 1
    assert lith.test_count == 1


def test_crashes_1() -> None:
    """timeout test for the 'crashes' interestingness test"""
    lith = lithium.Lithium()

    # check that --timeout works
    start_time = time.time()
    result = lith.main(
        [
            "--strategy",
            "check-only",
            "--testcase",
            "temp.js",
            "crashes",
            "--timeout",
            "1",
        ]
        + SLEEP_CMD
        + ["3"]
    )
    elapsed = time.time() - start_time
    assert result == 1
    assert elapsed >= 1
    assert lith.test_count == 1


def test_crashes_2(examples_path: Path) -> None:
    """crash test for the 'crashes' interestingness test"""
    lith = lithium.Lithium()

    # if a compiler is available, compile a simple crashing test program
    src = examples_path / "crash.c"
    exe = Path.cwd().resolve() / (
        "crash.exe" if platform.system() == "Windows" else "crash"
    )
    try:
        _compile(src, exe)
    except RuntimeError as exc:
        LOG.warning(exc)
        pytest.skip("compile 'crash.c' failed")
    result = lith.main(["--strategy", "check-only", "crashes", str(exe), "temp.js"])
    assert result == 0
    assert lith.test_count == 1


def test_diff_test_0() -> None:
    """test for the 'diff_test' interestingness test"""
    lith = lithium.Lithium()

    # test that the parameters "-a" and "-b" of diff_test work
    result = lith.main(
        [
            "--strategy",
            "check-only",
            "diff_test",
            "--timeout",
            "99",
            "-a",
            "flags_one",
            "-b",
            "flags_two_a flags_two_b",
        ]
        + LS_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_diff_test_1() -> None:
    """test for the 'diff_test' interestingness test"""
    lith = lithium.Lithium()

    # test that the parameters "-a" and "-b" of diff_test work
    result = lith.main(
        [
            "--strategy",
            "check-only",
            "diff_test",
            "-a",
            "'--fuzzing-safe'",
            "-b",
            "'--fuzzing-safe --ion-offthread-compile=off'",
        ]
        + LS_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_hangs_0() -> None:
    """test for the 'hangs' interestingness test"""
    lith = lithium.Lithium()

    # test that `sleep 3` hangs over 1s
    result = lith.main(
        ["--strategy", "check-only", "--testcase", "temp.js", "hangs", "--timeout", "1"]
        + SLEEP_CMD
        + ["3"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_hangs_1() -> None:
    """test for the 'hangs' interestingness test"""
    lith = lithium.Lithium()

    # test that `ls temp.js` does not hang over 1s
    result = lith.main(
        ["--strategy", "check-only", "hangs", "--timeout", "1"] + LS_CMD + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_outputs_true() -> None:
    """interestingness 'outputs' positive test"""
    lith = lithium.Lithium()

    # test that `ls temp.js` contains "temp.js"
    result = lith.main(
        ["--strategy", "check-only", "outputs", "--search", "temp.js"]
        + LS_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_outputs_in_bytes_true() -> None:
    """Test that output test properly identifies string in bytes object"""
    mock_run_data = MagicMock(RunData)
    mock_run_data.err = b""
    mock_run_data.out = b"magic bytes"
    with patch("lithium.interestingness.outputs.timed_run") as mock_timed_run:
        mock_timed_run.return_value = mock_run_data
        assert outputs.interesting(["-s", "magic bytes"] + LS_CMD)


def test_outputs_false() -> None:
    """interestingness 'outputs' negative test"""
    lith = lithium.Lithium()

    # test that `ls temp.js` does not contain "blah"
    result = lith.main(
        ["--strategy", "check-only", "outputs", "--search", "blah"]
        + LS_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_outputs_timeout() -> None:
    """interestingness 'outputs' --timeout test"""
    lith = lithium.Lithium()

    # check that --timeout works
    start_time = time.time()
    result = lith.main(
        [
            "--strategy",
            "check-only",
            "--testcase",
            "temp.js",
            "outputs",
            "--timeout",
            "1",
            "--search",
            "blah",
        ]
        + SLEEP_CMD
        + ["3"]
    )
    elapsed = time.time() - start_time
    assert result == 1
    assert elapsed >= 1
    assert lith.test_count == 1


def test_outputs_regex() -> None:
    """interestingness 'outputs' --regex test"""
    lith = lithium.Lithium()

    # test that regex matches work too
    result = lith.main(
        ["--strategy", "check-only", "outputs", "--search", r"^.*js\s?$", "--regex"]
        + LS_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_repeat_0() -> None:
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()
    with open("temp.js", "w") as tempf:
        tempf.write("hello")

    # Check for a known string
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "5", "outputs", "--search", "hello"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_repeat_1(caplog) -> None:
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()
    with open("temp.js", "w") as tempf:
        tempf.write("hello")

    # Look for a non-existent string, so the "repeat" test tries looping the maximum
    # number of iterations (5x)
    caplog.clear()
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "5", "outputs", "--search", "notfound"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1

    # scan the log output to see how many tests were performed
    found_count = 0
    last_count = 0
    for rec in caplog.records:
        message = rec.getMessage()
        if "Repeat number " in message:
            found_count += 1
            last_count = rec.args[0]
    assert found_count == 5  # Should have run 5x
    assert found_count == last_count  # We should have identical count outputs


def test_repeat_2() -> None:
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()

    # Check that replacements on the CLI work properly
    # Lower boundary - check that 0 (just outside [1]) is not found
    with open("temp.js", "w") as tempf1a:
        tempf1a.write("num0")
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "1", "outputs", "--timeout=9", "--search", "numREPEATNUM"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_repeat_3() -> None:
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()

    # Upper boundary - check that 2 (just outside [1]) is not found
    with open("temp.js", "w") as tempf1b:
        tempf1b.write("num2")
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "1", "outputs", "--timeout=9", "--search", "numREPEATNUM"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_repeat_4() -> None:
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()

    # Lower boundary - check that 0 (just outside [1,2]) is not found
    with open("temp.js", "w") as tempf2a:
        tempf2a.write("num0")
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "2", "outputs", "--timeout=9", "--search", "numREPEATNUM"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_repeat_5() -> None:
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()

    # Upper boundary - check that 3 (just outside [1,2]) is not found
    with open("temp.js", "w") as tempf2b:
        tempf2b.write("num3")
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "2", "outputs", "--timeout=9", "--search", "numREPEATNUM"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


@pytest.mark.parametrize(
    "pattern, expected",
    [
        ("B\nline C", "line B\nline C"),
        ("line B\nline C\n", "line B\nline C\n"),
        ("line A\nline", "line A\nline B"),
        ("\nline E\n", "\nline E\n"),
        ("line A", "line A"),
        ("line E", "line E"),
        ("line B", "line B"),
    ],
)
def test_interestingness_outputs_multiline(capsys, pattern, expected) -> None:
    """Tests for the 'outputs' interestingness test with multiline pattern"""
    lith = lithium.Lithium()

    with open("temp.js", "wb") as tmp_f:
        tmp_f.write(b"line A\nline B\nline C\nline D\nline E\n")

    capsys.readouterr()  # clear captured output buffers
    result = lith.main(
        [
            "outputs",
            "--search",
            pattern,
        ]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 0, f"{pattern!r} not found in {Path('temp.js').read_text()!r}"
    #    assert lith.test_count == 1
    captured = capsys.readouterr()
    assert f"[Found string in: {expected!r}]" in captured.out
