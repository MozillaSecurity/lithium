#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring,missing-param-doc,missing-type-doc
# pylint: disable=missing-return-doc,missing-return-type-doc
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, division

import collections
import logging
import math
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import pytest
if platform.system() != "Windows":
    winreg = None
elif sys.version_info.major == 2:
    import _winreg as winreg  # pylint: disable=import-error
else:
    import winreg  # pylint: disable=import-error

import lithium  # noqa pylint: disable=wrong-import-position

log = logging.getLogger("lithium_test")
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("flake8").setLevel(logging.WARNING)


# python 3 has unlimited precision integers
# restrict tests to 64-bit
if not hasattr(sys, "maxint"):
    sys.maxint = (1 << 64) - 1

if str is bytes:
    TEXT_T = unicode  # noqa: F821 pylint: disable=unicode-builtin,undefined-variable
else:
    TEXT_T = str


class TestCase(unittest.TestCase):

    def setUp(self):
        self.tmpd = tempfile.mkdtemp(prefix='lithiumtest')
        self.cwd = os.getcwd()
        os.chdir(self.tmpd)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmpd)

    if sys.version_info.major == 2:

        def assertRegex(self, *args, **kwds):  # pylint: disable=arguments-differ
            return self.assertRegexpMatches(*args, **kwds)  # pylint: disable=deprecated-method

        def assertRaisesRegex(self, *args, **kwds):  # pylint: disable=arguments-differ
            return self.assertRaisesRegexp(*args, **kwds)  # pylint: disable=deprecated-method

    if sys.version_info[:2] < (3, 4):
        #
        # polyfill adapted from https://github.com/python/cpython/blob/3.6/Lib/unittest/case.py
        #
        # This method is licensed as follows:
        #
        # Copyright (c) 1999-2003 Steve Purcell
        # Copyright (c) 2003-2010 Python Software Foundation
        # This module is free software, and you may redistribute it and/or modify
        # it under the same terms as Python itself, so long as this copyright message
        # and disclaimer are retained in their original form.
        #
        # IN NO EVENT SHALL THE AUTHOR BE LIABLE TO ANY PARTY FOR DIRECT, INDIRECT,
        # SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE USE OF
        # THIS CODE, EVEN IF THE AUTHOR HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH
        # DAMAGE.
        #
        # THE AUTHOR SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT
        # LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
        # PARTICULAR PURPOSE.  THE CODE PROVIDED HEREUNDER IS ON AN "AS IS" BASIS,
        # AND THERE IS NO OBLIGATION WHATSOEVER TO PROVIDE MAINTENANCE,
        # SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS.

        def assertLogs(self, logger=None, level=None):

            _LoggingWatcher = collections.namedtuple("_LoggingWatcher", ["records", "output"])

            class _CapturingHandler(logging.Handler):
                def __init__(self):
                    logging.Handler.__init__(self)
                    self.watcher = _LoggingWatcher([], [])

                def emit(self, record):
                    self.watcher.records.append(record)
                    self.watcher.output.append(self.format(record))

            class _AssertLogsContext(object):  # pylint: disable=too-few-public-methods
                LOGGING_FORMAT = "%(levelname)s:%(name)s:%(message)s"

                def __init__(self, test_case, logger_name, level):
                    self.test_case = test_case
                    self.logger = None
                    self.logger_name = logger_name
                    self.level = getattr(logging, level) if level else logging.INFO
                    self.msg = None
                    self.old = None
                    self.watcher = None

                def __enter__(self):
                    if isinstance(self.logger_name, logging.Logger):
                        self.logger = self.logger_name
                    else:
                        self.logger = logging.getLogger(self.logger_name)
                    handler = _CapturingHandler()
                    handler.setFormatter(logging.Formatter(self.LOGGING_FORMAT))
                    self.watcher = handler.watcher
                    self.old = (self.logger.handlers[:], self.logger.propagate, self.logger.level)
                    self.logger.handlers = [handler]
                    self.logger.setLevel(self.level)
                    self.logger.propagate = False
                    return handler.watcher

                def __exit__(self, exc_type, exc_value, tb):  # pylint: disable=inconsistent-return-statements
                    self.logger.handlers, self.logger.propagate = self.old[:2]
                    self.logger.setLevel(self.old[2])
                    if exc_type is not None:
                        return False
                    self.test_case.assertGreater(
                        len(self.watcher.records), 0,
                        "no logs of level %s or higher triggered on %s" % (
                            logging.getLevelName(self.level), self.logger.name))

            return _AssertLogsContext(self, logger, level)


class DisableWER(object):
    """Disable Windows Error Reporting for the duration of the context manager.

    ref: https://msdn.microsoft.com/en-us/library/bb513638.aspx
    """
    # pylint: disable=too-few-public-methods

    def __init__(self):
        self.wer_disabled = None
        self.wer_dont_show_ui = None

    def __enter__(self):
        if winreg is not None:
            wer = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\Windows Error Reporting", 0,
                                 winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE)
            # disable reporting to microsoft
            # this might disable dump generation altogether, which is not what we want
            self.wer_disabled = bool(winreg.QueryValueEx(wer, "Disabled")[0])
            if not self.wer_disabled:
                winreg.SetValueEx(wer, "Disabled", 0, winreg.REG_DWORD, 1)
            # don't show the crash UI (Debug/Close Application)
            self.wer_dont_show_ui = bool(winreg.QueryValueEx(wer, "DontShowUI")[0])
            if not self.wer_dont_show_ui:
                winreg.SetValueEx(wer, "DontShowUI", 0, winreg.REG_DWORD, 1)

    def __exit__(self, exc_type, exc_value, tb):
        # restore previous settings
        if winreg is not None:
            wer = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\Windows Error Reporting", 0,
                                 winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE)
            if not self.wer_disabled:
                winreg.SetValueEx(wer, "Disabled", 0, winreg.REG_DWORD, 0)
            if not self.wer_dont_show_ui:
                winreg.SetValueEx(wer, "DontShowUI", 0, winreg.REG_DWORD, 0)


class DummyInteresting(object):
    def init(self, conditionArgs):
        pass

    def interesting(self, conditionArgs, tempPrefix):
        pass

    def cleanup(self, conditionArgs):
        pass


def ispow2(n):
    """Simple version for testing
    """
    assert isinstance(n, int) or n.is_integer(), "ispow2() only works for integers, %r is not an integer" % n
    assert n >= 1, "domain error"
    orig = n
    result = True
    while n > 1:
        if n % 2:
            result = False
            break
        n //= 2
    # if the input is representable as a float, compare the result to math library
    if orig <= sys.float_info.max:
        math_result = math.log(orig) / math.log(2)
        # diff to the next closest integer
        diff = abs(math_result - round(math_result))  # pylint: disable=round-builtin
        math_result = diff < 10**-(sys.float_info.dig - 1)  # float_info.dig is the # of decimal digits representable
        assert result == math_result, "ispow2(n) did not match math.log(n)/math.log(2) for n = %d" % orig
    return result


def divceil(n, d):
    """Simple version for testing
    """
    q = n // d
    r = n % d
    result = q + (1 if r else 0)
    # if the inputs are representable as a float, compare the result to math library
    if n <= sys.float_info.max and d <= sys.float_info.max:
        math_result = math.ceil(1.0 * n / d)
        assert result == math_result, "divceil(n,d) did not match math.ceil(n/d) for n = %d, d = %d" % (n, d)
    return result


class HelperTests(TestCase):

    def test_divideRoundingUp(self):
        for _ in range(10000):
            n = random.randint(1, sys.maxint)  # pylint: disable=sys-max-int
            d = random.randint(1, n)
            try:
                self.assertEqual(divceil(n, d), lithium.divideRoundingUp(n, d))
                self.assertEqual(1, lithium.divideRoundingUp(n, n))
                self.assertEqual(0, lithium.divideRoundingUp(0, n))
                self.assertEqual(2, lithium.divideRoundingUp(n + 1, n))
            except Exception:
                log.debug("n = %d, d = %d", n, d)
                raise

    def test_isPowerOfTwo(self):
        self.assertFalse(lithium.isPowerOfTwo(0))
        # try all integers [1,10000)
        for i in range(1, 10000):
            try:
                self.assertEqual(ispow2(i), lithium.isPowerOfTwo(i))
            except Exception:
                log.debug("i = %d", i)
                raise
        # try 10000 random integers >= 10000
        for _ in range(10000):
            r = random.randint(10000, sys.maxint)  # pylint: disable=sys-max-int
            try:
                self.assertEqual(ispow2(r), lithium.isPowerOfTwo(r))
            except Exception:
                log.debug("r = %d", r)
                raise

    def test_largestPowerOfTwoSmallerThan(self):
        self.assertEqual(1, lithium.largestPowerOfTwoSmallerThan(0))

        def check_result(r, i):
            # check that it is a power of two
            self.assertTrue(ispow2(r))
            # check that it is < i
            if i != 1:
                self.assertLess(r, i)
            # check that the next power of 2 is >= i
            self.assertGreaterEqual(r * 2, i)
        # try all integers [1,10000)
        for i in range(1, 10000):
            try:
                check_result(lithium.largestPowerOfTwoSmallerThan(i), i)
            except Exception:
                log.debug("i = %d", i)
                raise
        # try 10000 random integers >= 10000
        for _ in range(10000):
            r = random.randint(10000, sys.maxint)  # pylint: disable=sys-max-int
            try:
                check_result(lithium.largestPowerOfTwoSmallerThan(r), r)
            except Exception:
                log.debug("r = %d", r)
                raise


class InterestingnessTests(TestCase):
    cat_cmd = [sys.executable, "-c", ("import sys;"
                                      "[sys.stdout.write(f.read())"
                                      " for f in"
                                      "     ([open(a) for a in sys.argv[1:]] or"
                                      "      [sys.stdin])"
                                      "]")]
    ls_cmd = [sys.executable, "-c", ("import glob,itertools,os,sys;"
                                     "[sys.stdout.write(p+'\\n')"
                                     " for p in"
                                     "     (itertools.chain.from_iterable(glob.glob(d) for d in sys.argv[1:])"
                                     "      if len(sys.argv) > 1"
                                     "      else os.listdir('.'))"
                                     "]")]
    sleep_cmd = [sys.executable, "-c", "import sys,time;time.sleep(int(sys.argv[1]))"]
    if platform.system() == "Windows":
        compilers_to_try = ["cl", "clang", "gcc", "cc"]
    else:
        compilers_to_try = ["clang", "gcc", "cc"]

    @classmethod
    def _compile(cls, in_path, out_path):
        """Try to compile a source file using any available C/C++ compiler.

        Args:
            in_path (str): Source file to compile from
            out_path (str): Executable file to compile to

        Raises:
            RuntimeError: Raises this exception if the compilation fails or if the compiler cannot be found
        """
        assert os.path.isfile(in_path)
        for compiler in cls.compilers_to_try:
            try:
                out_param = "/Fe" if compiler == "cl" else "-o"
                out = subprocess.check_output([compiler, out_param + out_path, in_path], stderr=subprocess.STDOUT)
                for line in out.splitlines():
                    log.debug("%s: %s", compiler, line)
                cls.compilers_to_try = [compiler]  # this compiler worked, never try any others
                return
            except OSError:
                log.debug("%s not found", compiler)
            except subprocess.CalledProcessError as exc:
                for line in exc.output.splitlines():
                    log.debug("%s: %s", compiler, line)
        # all of compilers we tried have failed :(
        raise RuntimeError("Compile failed")

    def test_crashes(self):
        """Tests for the 'crashes' interestingness test"""
        l = lithium.Lithium()  # noqa: E741
        with open("temp.js", "w"):
            pass

        # check that `ls` doesn't crash
        result = l.main(["crashes"] + self.ls_cmd + ["temp.js"])
        self.assertEqual(result, 1)

        # check that --timeout works
        start_time = time.time()
        result = l.main(["--testcase", "temp.js", "crashes", "--timeout", "1"] + self.sleep_cmd + ["3"])
        elapsed = time.time() - start_time
        self.assertEqual(result, 1)
        self.assertGreaterEqual(elapsed, 1)

        # if a compiler is available, compile a simple crashing test program
        try:
            src = os.path.join(os.path.dirname(__file__), os.pardir, "src", "lithium", "docs", "examples", "crash.c")
            exe = "crash.exe" if platform.system() == "Windows" else "./crash"
            self._compile(src, exe)
            with DisableWER():
                result = l.main(["crashes", exe, "temp.js"])
            self.assertEqual(result, 0)
        except RuntimeError as exc:
            log.warning(exc)

    def test_diff_test(self):
        """Tests for the 'diff_test' interestingness test"""
        l = lithium.Lithium()  # noqa: E741
        with open("temp.js", "w"):
            pass

        # test that the parameters "-a" and "-b" of diff_test work
        result = l.main(["diff_test", "--timeout", "99", "-a", "flags_one",
                         "-b", "flags_two_a flags_two_b"] + self.ls_cmd + ["temp.js"])
        self.assertEqual(result, 0)
        result = l.main(["diff_test", "--a-args", "flags_one_a flags_one_b",
                         "--b-args", "flags_two"] + self.ls_cmd + ["temp.js"])
        self.assertEqual(result, 0)

    def test_hangs(self):
        """Tests for the 'hangs' interestingness test"""
        l = lithium.Lithium()  # noqa: E741
        with open("temp.js", "w"):
            pass

        # test that `sleep 3` hangs over 1s
        result = l.main(["--testcase", "temp.js", "hangs", "--timeout", "1"] + self.sleep_cmd + ["3"])
        self.assertEqual(result, 0)

        # test that `ls temp.js` does not hang over 1s
        result = l.main(["hangs", "--timeout", "1"] + self.ls_cmd + ["temp.js"])
        self.assertEqual(result, 1)

    def test_outputs_true(self):
        """interestingness 'outputs' positive test"""
        l = lithium.Lithium()  # noqa: E741
        with open("temp.js", "w"):
            pass

        # test that `ls temp.js` contains "temp.js"
        result = l.main(["outputs", "temp.js"] + self.ls_cmd + ["temp.js"])
        assert result == 0

    def test_outputs_false(self):
        """interestingness 'outputs' negative test"""
        l = lithium.Lithium()  # noqa: E741
        with open("temp.js", "w"):
            pass

        # test that `ls temp.js` does not contain "blah"
        result = l.main(["outputs", "blah"] + self.ls_cmd + ["temp.js"])
        assert result == 1

    def test_outputs_timeout(self):
        """interestingness 'outputs' --timeout test"""
        l = lithium.Lithium()  # noqa: E741
        with open("temp.js", "w"):
            pass

        # check that --timeout works
        start_time = time.time()
        result = l.main(["--testcase", "temp.js", "outputs", "--timeout", "1", "blah"] + self.sleep_cmd + ["3"])
        elapsed = time.time() - start_time
        assert result == 1
        assert elapsed >= 1

    def test_outputs_regex(self):
        """interestingness 'outputs' --regex test"""
        l = lithium.Lithium()  # noqa: E741
        with open("temp.js", "w"):
            pass

        # test that regex matches work too
        result = l.main(["outputs", "--regex", r"^.*js\s?$"] + self.ls_cmd + ["temp.js"])
        assert result == 0

    def test_repeat(self):
        """Tests for the 'repeat' interestingness test"""
        l = lithium.Lithium()  # noqa: E741
        with open("temp.js", "w") as tempf:
            tempf.write("hello")

        # Check for a known string
        result = l.main(["repeat", "5", "outputs", "hello"] + self.cat_cmd + ["temp.js"])
        self.assertEqual(result, 0)

        # Look for a non-existent string, so the "repeat" test tries looping the maximum number of iterations (5x)
        with self.assertLogs("lithium") as test_logs:
            result = l.main(["repeat", "5", "outputs", "notfound"] + self.cat_cmd + ["temp.js"])
            self.assertEqual(result, 1)
            found_count = 0
            last_count = 0
            # scan the log output to see how many tests were performed
            for rec in test_logs.records:
                message = rec.getMessage()
                if "Repeat number " in message:
                    found_count += 1
                    last_count = rec.args[0]
            self.assertEqual(found_count, 5)  # Should have run 5x
            self.assertEqual(found_count, last_count)  # We should have identical count outputs

            # Check that replacements on the CLI work properly
            # Lower boundary - check that 0 (just outside [1]) is not found
            with open("temp1a.js", "w") as tempf1a:
                tempf1a.write("num0")
            result = l.main(["repeat", "1", "outputs", "--timeout=9", "numREPEATNUM"] + self.cat_cmd + ["temp1a.js"])
            self.assertEqual(result, 1)

            # Upper boundary - check that 2 (just outside [1]) is not found
            with open("temp1b.js", "w") as tempf1b:
                tempf1b.write("num2")
            result = l.main(["repeat", "1", "outputs", "--timeout=9", "numREPEATNUM"] + self.cat_cmd + ["temp1b.js"])
            self.assertEqual(result, 1)

            # Lower boundary - check that 0 (just outside [1,2]) is not found
            with open("temp2a.js", "w") as tempf2a:
                tempf2a.write("num0")
            result = l.main(["repeat", "2", "outputs", "--timeout=9", "numREPEATNUM"] + self.cat_cmd + ["temp2a.js"])
            self.assertEqual(result, 1)

            # Upper boundary - check that 3 (just outside [1,2]) is not found
            with open("temp2b.js", "w") as tempf2b:
                tempf2b.write("num3")
            result = l.main(["repeat", "2", "outputs", "--timeout=9", "numREPEATNUM"] + self.cat_cmd + ["temp2b.js"])
            self.assertEqual(result, 1)


@pytest.mark.parametrize("pattern, expected", [("B\nline C", "line B\nline C"),
                                               ("line B\nline C\n", "line B\nline C\n"),
                                               ("line A\nline", "line A\nline B"),
                                               ("\nline E\n", "\nline E\n"),
                                               ("line A", "line A"),
                                               ("line E", "line E"),
                                               ("line B", "line B")])
def test_interestingness_outputs_multiline(capsys, pattern, expected):
    """Tests for the 'outputs' interestingness test with multiline pattern"""
    l = lithium.Lithium()  # noqa: E741

    with open("temp.js", "wb") as tmp_f:
        tmp_f.write(b"line A\nline B\nline C\nline D\nline E\n")

    capsys.readouterr()  # clear captured output buffers
    expected = TEXT_T(expected)
    result = l.main(["outputs", pattern] + InterestingnessTests.cat_cmd + ["temp.js"])
    assert result == 0, "%r not found in %r" % (pattern, open("temp.js").read())
    out, _ = capsys.readouterr()
    expected = '[Found string in: %r]' % (expected,)
    assert expected in out


class LithiumTests(TestCase):

    def test_executable(self):
        with self.assertRaisesRegex(SystemExit, "0"):
            lithium.Lithium().main(["-h"])

    def test_class(self):
        l = lithium.Lithium()  # noqa: E741
        with open("empty.txt", "w"):
            pass

        class Interesting(DummyInteresting):
            init_called = False
            interesting_called = False
            cleanup_called = False

            def init(sub, conditionArgs):  # pylint: disable=no-self-argument
                sub.init_called = True

            def interesting(sub, conditionArgs, tempPrefix):  # pylint: disable=no-self-argument
                sub.interesting_called = True
                return True

            def cleanup(sub, conditionArgs):  # pylint: disable=no-self-argument
                sub.cleanup_called = True
        inter = Interesting()
        l.conditionScript = inter
        l.conditionArgs = ["empty.txt"]
        l.strategy = lithium.CheckOnly()
        l.testcase = lithium.TestcaseLine()
        l.testcase.readTestcase("empty.txt")
        self.assertEqual(l.run(), 0)
        self.assertTrue(inter.init_called)
        self.assertTrue(inter.interesting_called)
        self.assertTrue(inter.cleanup_called)

    def test_empty(self):
        l = lithium.Lithium()  # noqa: E741
        with open("empty.txt", "w"):
            pass

        class Interesting(DummyInteresting):
            inter = False

            def interesting(sub, conditionArgs, tempPrefix):  # pylint: disable=no-self-argument
                return sub.inter
        l.conditionScript = Interesting()
        l.strategy = lithium.Minimize()
        l.testcase = lithium.TestcaseLine()
        l.testcase.readTestcase("empty.txt")
        with self.assertLogs("lithium") as logs:
            self.assertEqual(l.run(), 1)
        self.assertIn("INFO:lithium:Lithium result: the original testcase is not 'interesting'!", logs.output)
        Interesting.inter = True
        with self.assertLogs("lithium") as logs:
            self.assertEqual(l.run(), 0)
        self.assertIn("INFO:lithium:The file has 0 lines so there's nothing for Lithium to try to remove!", logs.output)

    def test_arithmetic(self):
        path = os.path.join(os.path.dirname(__file__), os.pardir, "src", "lithium", "docs", "examples", "arithmetic")
        shutil.copyfile(os.path.join(path, "11.txt"), "11.txt")
        result = lithium.Lithium().main([os.path.join(path, "product_divides.py"), "35", "11.txt"])
        self.assertEqual(result, 0)
        with open("11.txt") as f:
            self.assertEqual(f.read(), "2\n\n# DDBEGIN\n5\n7\n# DDEND\n\n2\n")
        shutil.copyfile(os.path.join(path, "11.txt"), "11.txt")
        result = lithium.Lithium().main(["-c", os.path.join(path, "product_divides.py"), "35", "11.txt"])
        self.assertEqual(result, 0)
        with open("11.txt") as f:
            self.assertEqual(f.read(), "2\n\n# DDBEGIN\n5\n7\n# DDEND\n\n2\n")


class StrategyTests(TestCase):

    def test_minimize(self):
        class Interesting(DummyInteresting):

            def interesting(sub, conditionArgs, tempPrefix):  # pylint: disable=no-self-argument
                with open("a.txt", "rb") as f:
                    return b"o\n" in f.read()
        l = lithium.Lithium()  # noqa: E741
        l.conditionScript = Interesting()
        l.strategy = lithium.Minimize()
        for testcaseType in (lithium.TestcaseChar, lithium.TestcaseLine, lithium.TestcaseSymbol):
            log.info("Trying with testcase type %s:", testcaseType.__name__)
            with open("a.txt", "wb") as f:
                f.write(b"x\n\nx\nx\no\nx\nx\nx\n")
            l.testcase = testcaseType()
            l.testcase.readTestcase("a.txt")
            self.assertEqual(l.run(), 0)
            with open("a.txt", "rb") as f:
                self.assertEqual(f.read(), b"o\n")

    def test_minimize_around(self):
        class Interesting(DummyInteresting):

            def interesting(sub, conditionArgs, tempPrefix):  # pylint: disable=no-self-argument
                with open("a.txt", "rb") as f:
                    data = f.read()
                    return b"o\n" in data and len(set(data.split(b"o\n"))) == 1
        l = lithium.Lithium()  # noqa: E741
        l.conditionScript = Interesting()
        l.strategy = lithium.MinimizeSurroundingPairs()
        for testcaseType in (lithium.TestcaseChar, lithium.TestcaseLine, lithium.TestcaseSymbol):
            log.info("Trying with testcase type %s:", testcaseType.__name__)
            with open("a.txt", "wb") as f:
                f.write(b"x\nx\nx\no\nx\nx\nx\n")
            l.testcase = testcaseType()
            l.testcase.readTestcase("a.txt")
            self.assertEqual(l.run(), 0)
            with open("a.txt", "rb") as f:
                self.assertEqual(f.read(), b"o\n")

    def test_minimize_balanced(self):
        class Interesting(DummyInteresting):

            def interesting(sub, conditionArgs, tempPrefix):  # pylint: disable=no-self-argument
                with open("a.txt", "rb") as f:
                    data = f.read()
                    if b"o\n" in data:
                        a, b = data.split(b"o\n")
                        return (a.count(b"{") == b.count(b"}")) and \
                               (a.count(b"(") == b.count(b")")) and \
                               (a.count(b"[") == b.count(b"]"))
                    return False
        l = lithium.Lithium()  # noqa: E741
        l.conditionScript = Interesting()
        l.strategy = lithium.MinimizeBalancedPairs()
        for testcaseType in (lithium.TestcaseChar, lithium.TestcaseLine, lithium.TestcaseSymbol):
            log.info("Trying with testcase type %s:", testcaseType.__name__)
            with open("a.txt", "wb") as f:
                f.write(b"[\n[\nxxx{\no\n}\n]\n]\n")
            l.testcase = testcaseType()
            l.testcase.readTestcase("a.txt")
            self.assertEqual(l.run(), 0)
            with open("a.txt", "rb") as f:
                self.assertEqual(f.read(), b"o\n")

    def test_replace_properties(self):
        valid_reductions = (
            # original: this.list, prototype.push, prototype.last
            b"function Foo() {\n  this.list = [];\n}\n" +
            b"Foo.prototype.push = function(a) {\n  this.list.push(a);\n}\n" +
            b"Foo.prototype.last = function() {\n  return this.list.pop();\n}\n",
            #           this.list, prototype.push,           last
            b"function Foo() {\n  this.list = [];\n}\n" +
            b"Foo.prototype.push = function(a) {\n  this.list.push(a);\n}\n" +
            b"last = function() {\n  return this.list.pop();\n}\n",
            #           this.list,           push, prototype.last
            b"function Foo() {\n  this.list = [];\n}\n" +
            b"push = function(a) {\n  this.list.push(a);\n}\n" +
            b"Foo.prototype.last = function() {\n  return this.list.pop();\n}\n",
            #           this.list,           push,           last
            b"function Foo() {\n  this.list = [];\n}\n" +
            b"push = function(a) {\n  this.list.push(a);\n}\n" +
            b"last = function() {\n  return this.list.pop();\n}\n",
            #                list, prototype.push, prototype.last
            b"function Foo() {\n  list = [];\n}\n" +
            b"Foo.prototype.push = function(a) {\n  list.push(a);\n}\n" +
            b"Foo.prototype.last = function() {\n  return list.pop();\n}\n",
            #                list, prototype.push,           last
            b"function Foo() {\n  list = [];\n}\n" +
            b"Foo.prototype.push = function(a) {\n  list.push(a);\n}\n" +
            b"last = function() {\n  return list.pop();\n}\n",
            #                list,           push, prototype.last
            b"function Foo() {\n  list = [];\n}\n" +
            b"push = function(a) {\n  list.push(a);\n}\n" +
            b"Foo.prototype.last = function() {\n  return list.pop();\n}\n",
            # reduced:       list,           push,           last
            b"function Foo() {\n  list = [];\n}\n" +
            b"push = function(a) {\n  list.push(a);\n}\n" +
            b"last = function() {\n  return list.pop();\n}\n"
        )

        class Interesting(DummyInteresting):

            def interesting(sub, conditionArgs, tempPrefix):  # pylint: disable=no-self-argument
                with open("a.txt", "rb") as f:
                    return f.read() in valid_reductions
        l = lithium.Lithium()  # noqa: E741
        for testcaseType in (lithium.TestcaseChar, lithium.TestcaseLine, lithium.TestcaseSymbol):
            log.info("Trying with testcase type %s:", testcaseType.__name__)
            with open("a.txt", "wb") as f:
                f.write(valid_reductions[0])
            l.conditionScript = Interesting()
            l.strategy = lithium.ReplacePropertiesByGlobals()
            l.testcase = testcaseType()
            l.testcase.readTestcase("a.txt")
            self.assertEqual(l.run(), 0)
            with open("a.txt", "rb") as f:
                if testcaseType is lithium.TestcaseChar:
                    # Char doesn't give this strategy enough to work with
                    self.assertEqual(f.read(), valid_reductions[0])
                else:
                    self.assertEqual(f.read(), valid_reductions[-1])

    def test_replace_arguments(self):
        valid_reductions = (
            b"function foo(a,b) {\n  list = a + b;\n}\nfoo(2,3)\n",
            b"function foo(a) {\n  list = a + b;\n}\nb = 3;\nfoo(2)\n",
            b"function foo(a) {\n  list = a + b;\n}\nb = 3;\nfoo(2,3)\n",
            b"function foo(b) {\n  list = a + b;\n}\na = 2;\nfoo(3)\n",
            b"function foo() {\n  list = a + b;\n}\na = 2;\nb = 3;\nfoo(2,3)\n",
            b"function foo() {\n  list = a + b;\n}\na = 2;\nb = 3;\nfoo()\n"
        )

        class Interesting(DummyInteresting):

            def interesting(sub, conditionArgs, tempPrefix):  # pylint: disable=no-self-argument
                with open("a.txt", "rb") as f:
                    return f.read() in valid_reductions
        l = lithium.Lithium()  # noqa: E741
        l.conditionScript = Interesting()
        l.strategy = lithium.ReplaceArgumentsByGlobals()
        for testcaseType in (lithium.TestcaseChar, lithium.TestcaseLine, lithium.TestcaseSymbol):
            log.info("Trying with testcase type %s:", testcaseType.__name__)
            with open("a.txt", "wb") as f:
                f.write(valid_reductions[0])
            l.testcase = testcaseType()
            l.testcase.readTestcase("a.txt")
            self.assertEqual(l.run(), 0)
            with open("a.txt", "rb") as f:
                if testcaseType is lithium.TestcaseChar:
                    # Char doesn't give this strategy enough to work with
                    self.assertEqual(f.read(), valid_reductions[0])
                else:
                    self.assertEqual(f.read(), valid_reductions[-1])

    def test_minimize_collapse_braces(self):
        class Interesting(DummyInteresting):

            def interesting(sub, conditionArgs, tempPrefix):  # pylint: disable=no-self-argument
                with open("a.txt", "rb") as f:
                    data = f.read()
                    if conditionArgs == 'NEEDS_BRACE':
                        return data.count(b"{") == 1 and data.count(b"{") == data.count(b"}")
                    if conditionArgs == 'NO_BRACE':
                        if b"o\n" in data:
                            return data.count(b"{") == data.count(b"}")
                    return False
        # CollapseEmptyBraces only applies to line-based reduction
        log.info("Trying with testcase type %s:", lithium.TestcaseLine.__name__)
        for test_type in ['NEEDS_BRACE', 'NO_BRACE']:
            l = lithium.Lithium()  # noqa: E741
            l.conditionScript = Interesting()
            l.conditionArgs = test_type
            l.strategy = lithium.CollapseEmptyBraces()
            with open("a.txt", "wb") as f:
                f.write(b"x\nxxx{\nx\n}\no\n")
            l.testcase = lithium.TestcaseLine()
            l.testcase.readTestcase("a.txt")
            self.assertEqual(l.run(), 0)
            if test_type == 'NEEDS_BRACE':
                self.assertEqual(l.testCount, 15)
                with open("a.txt", "rb") as f:
                    self.assertEqual(f.read(), b"xxx{ }\n")
            elif test_type == 'NO_BRACE':
                self.assertEqual(l.testCount, 16)
                with open("a.txt", "rb") as f:
                    self.assertEqual(f.read(), b"o\n")


class TestcaseTests(TestCase):

    def test_line(self):
        t = lithium.TestcaseLine()
        with open("a.txt", "wb") as f:
            f.write(b"hello")
        t.readTestcase("a.txt")
        os.unlink("a.txt")
        self.assertFalse(os.path.isfile("a.txt"))
        t.writeTestcase()
        with open("a.txt", "rb") as f:
            self.assertEqual(f.read(), b"hello")
        self.assertEqual(t.filename, "a.txt")
        self.assertEqual(t.extension, ".txt")
        self.assertEqual(t.before, b"")
        self.assertEqual(t.parts, [b"hello"])
        self.assertEqual(t.after, b"")
        t.writeTestcase("b.txt")
        with open("b.txt", "rb") as f:
            self.assertEqual(f.read(), b"hello")

    def test_line_dd(self):
        t = lithium.TestcaseLine()
        with open("a.txt", "wb") as f:
            f.write(b"pre\n")
            f.write(b"DDBEGIN\n")
            f.write(b"data\n")
            f.write(b"2\n")
            f.write(b"DDEND\n")
            f.write(b"post\n")
        t.readTestcase("a.txt")
        self.assertEqual(t.before, b"pre\nDDBEGIN\n")
        self.assertEqual(t.parts, [b"data\n", b"2\n"])
        self.assertEqual(t.after, b"DDEND\npost\n")

    def test_char_dd(self):
        t = lithium.TestcaseChar()
        with open("a.txt", "wb") as f:
            f.write(b"pre\n")
            f.write(b"DDBEGIN\n")
            f.write(b"data\n")
            f.write(b"2\n")
            f.write(b"DDEND\n")
            f.write(b"post\n")
        t.readTestcase("a.txt")
        self.assertEqual(t.before, b"pre\nDDBEGIN\n")
        self.assertEqual(t.parts, [b"d", b"a", b"t", b"a", b"\n", b"2"])
        self.assertEqual(t.after, b"\nDDEND\npost\n")

    def test_jsstr(self):
        """Test that the TestcaseJsStr class splits JS strings properly"""
        t = lithium.TestcaseJsStr()
        with open("a.txt", "wb") as f:
            f.write(b"pre\n")
            f.write(b"DDBEGIN\n")
            f.write(b"data\n")
            f.write(b"2\n")
            f.write(b"'\\u{123}\"1\\x32\\023\n'\n")  # a str with some escapes
            f.write(b'""\n')  # empty string
            f.write(b'"\\u12345Xyz"\n')  # another str with the last escape format
            f.write(b'Data\xFF\n')
            f.write(b'"x\xFF" something\n')  # last str
            f.write(b"DDEND\n")
            f.write(b"post\n")
        t.readTestcase("a.txt")
        self.assertEqual(t.before, b"pre\nDDBEGIN\ndata\n2\n'")
        self.assertEqual(t.parts, [b"\\u{123}", b"\"", b"1", b"\\x32", b"\\0", b"2", b"3", b"\n",  # first JS str
                                   b"'\n\"\"\n\"",  # empty string contains no chars, included with in-between data
                                   b"\\u1234", b"5", b"X", b"y", b"z",  # next JS str
                                   b"\"\nData\xFF\n\"",
                                   b"x", b"\xFF"])  # last JS str
        self.assertEqual(t.after, b"\" something\nDDEND\npost\n")
        with open("a.txt", "wb") as f:
            f.write(b"'xabcx'")
        t.readTestcase("a.txt")
        assert t.before == b"'"
        assert t.parts == [b"x", b"a", b"b", b"c", b"x"]
        assert t.after == b"'"
        with open("a.txt", "wb") as f:
            f.write(b"'x'abcx'")
        t.readTestcase("a.txt")
        assert t.before == b"'"
        assert t.parts == [b"x"]
        assert t.after == b"'abcx'"
        with open("a.txt", "wb") as f:
            f.write(b"'x\"abc\"x")
        t.readTestcase("a.txt")
        assert t.before == b"'x\""
        assert t.parts == [b"a", b"b", b"c"]
        assert t.after == b"\"x"

    def test_symbol(self):
        t = lithium.TestcaseSymbol()
        with open("a.txt", "wb") as f:
            f.write(b"pre\n")
            f.write(b"DDBEGIN\n")
            f.write(b"d{a}ta\n")
            f.write(b"2\n")
            f.write(b"DDEND\n")
            f.write(b"post\n")
        t.readTestcase("a.txt")
        self.assertEqual(t.before, b"pre\nDDBEGIN\n")
        self.assertEqual(t.parts, [b"d{", b"a", b"}ta\n", b"2\n"])
        self.assertEqual(t.after, b"DDEND\npost\n")
        with open("a.txt", "wb") as f:
            f.write(b"pre\n")
            f.write(b"DDBEGIN\n")
            f.write(b"{data\n")
            f.write(b"2}\n}")
            f.write(b"DDEND\n")
            f.write(b"post\n")
        t.readTestcase("a.txt")
        self.assertEqual(t.before, b"pre\nDDBEGIN\n")
        self.assertEqual(t.parts, [b"{", b"data\n", b"2", b"}\n"])
        self.assertEqual(t.after, b"}DDEND\npost\n")

    def test_errors(self):
        with open("a.txt", "w") as f:
            f.write("DDEND\n")
        t = lithium.TestcaseLine()
        with self.assertRaisesRegex(lithium.LithiumError,
                                    r"^The testcase \(a\.txt\) has a line containing 'DDEND' without"):
            t.readTestcase("a.txt")
        with open("a.txt", "w") as f:
            f.write("DDBEGIN DDEND\n")
        with self.assertRaisesRegex(lithium.LithiumError,
                                    r"^The testcase \(a\.txt\) has a line containing 'DDEND' without"):
            t.readTestcase("a.txt")
        with open("a.txt", "w") as f:
            f.write("DDEND DDBEGIN\n")
        with self.assertRaisesRegex(lithium.LithiumError,
                                    r"^The testcase \(a\.txt\) has a line containing 'DDEND' without"):
            t.readTestcase("a.txt")
        with open("a.txt", "w") as f:
            f.write("DDBEGIN\n")
        with self.assertRaisesRegex(lithium.LithiumError,
                                    r"^The testcase \(a\.txt\) has a line containing 'DDBEGIN' but no"):
            t.readTestcase("a.txt")
