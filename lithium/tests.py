import os
import shutil
import sys
import tempfile
import unittest

import lithium


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

