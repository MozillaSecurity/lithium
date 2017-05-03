import logging
import math
import os
import random
import shutil
import sys
import tempfile
import unittest

import lithium


log = logging.getLogger("lithium_test")
logging.basicConfig(level=logging.DEBUG)


# python 3 has unlimited precision integers
# restrict tests to 64-bit
if not hasattr(sys, "maxint"):
    sys.maxint = (1<<64)-1


class TestCase(unittest.TestCase):

    def setUp(self):
        self.tmpd = tempfile.mkdtemp(prefix='lithiumtest')
        self.cwd = os.getcwd()
        os.chdir(self.tmpd)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmpd)

    if sys.version_info.major == 2:

        def assertRegex(self, *args, **kwds):
            return self.assertRegexpMatches(*args, **kwds)

        def assertRaisesRegex(self, *args, **kwds):
            return self.assertRaisesRegexp(*args, **kwds)


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
        diff = abs(math_result - round(math_result)) # diff to the next closest integer
        math_result = diff < 10**-(sys.float_info.dig - 1) # float_info.dig is the # of decimal digits representable
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
                self.assertEqual(2, lithium.divideRoundingUp(n+1, n))
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
            def init(sub, conditionArgs):
                sub.init_called = True
            def interesting(sub, conditionArgs, tempPrefix):
                sub.interesting_called = True
                return True
            def cleanup(sub, conditionArgs):
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

    def test_arithmetic(self):
        path = os.path.join(os.path.dirname(lithium.__file__), "examples", "arithmetic")
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
        with self.assertRaisesRegex(lithium.LithiumError, r"^The testcase \(a\.txt\) has a line containing 'DDEND' without"):
            t.readTestcase("a.txt")
        with open("a.txt", "w") as f:
            f.write("DDBEGIN DDEND\n")
        with self.assertRaisesRegex(lithium.LithiumError, r"^The testcase \(a\.txt\) has a line containing 'DDEND' without"):
            t.readTestcase("a.txt")
        with open("a.txt", "w") as f:
            f.write("DDEND DDBEGIN\n")
        with self.assertRaisesRegex(lithium.LithiumError, r"^The testcase \(a\.txt\) has a line containing 'DDEND' without"):
            t.readTestcase("a.txt")
        with open("a.txt", "w") as f:
            f.write("DDBEGIN\n")
        with self.assertRaisesRegex(lithium.LithiumError, r"^The testcase \(a\.txt\) has a line containing 'DDBEGIN' but no"):
            t.readTestcase("a.txt")

