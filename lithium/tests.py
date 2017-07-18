#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring,too-few-public-methods
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import collections
import logging
import math
import os
import random
import shutil
import sys
import tempfile
import unittest

from . import lithium

log = logging.getLogger("lithium_test")
logging.basicConfig(level=logging.DEBUG)


# python 3 has unlimited precision integers
# restrict tests to 64-bit
if not hasattr(sys, "maxint"):
    sys.maxint = (1 << 64) - 1


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

            class _AssertLogsContext(object):
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

                def __exit__(self, exc_type, exc_value, tb):
                    self.logger.handlers, self.logger.propagate = self.old[:2]
                    self.logger.setLevel(self.old[2])
                    if exc_type is not None:
                        return False
                    self.test_case.assertGreater(
                        len(self.watcher.records), 0,
                        "no logs of level %s or higher triggered on %s" % (
                            logging.getLevelName(self.level), self.logger.name))

            return _AssertLogsContext(self, logger, level)


class DummyInteresting(object):
    def init(self, conditionArgs):
        pass

    def interesting(self, conditionArgs, tempPrefix):
        pass

    def cleanup(self, conditionArgs):
        pass


def ispow2(n):
    """
    simple version for testing
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
        diff = abs(math_result - round(math_result))  # diff to the next closest integer
        math_result = diff < 10**-(sys.float_info.dig - 1)  # float_info.dig is the # of decimal digits representable
        assert result == math_result, "ispow2(n) did not match math.log(n)/math.log(2) for n = %d" % orig
    return result


def divceil(n, d):
    """
    simple version for testing
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
            n = random.randint(1, sys.maxint)
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
            r = random.randint(10000, sys.maxint)
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
            r = random.randint(10000, sys.maxint)
            try:
                check_result(lithium.largestPowerOfTwoSmallerThan(r), r)
            except Exception:
                log.debug("r = %d", r)
                raise


class LithiumTests(TestCase):

    def test_executable(self):
        with self.assertRaisesRegex(SystemExit, "0"):
            lithium.Lithium().main(["-h"])

    def test_class(self):
        l = lithium.Lithium()
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
        l = lithium.Lithium()
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
        path = os.path.join(os.path.dirname(__file__), "examples", "arithmetic")
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
        l = lithium.Lithium()
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
        l = lithium.Lithium()
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
        l = lithium.Lithium()
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
        l = lithium.Lithium()
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
        l = lithium.Lithium()
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
