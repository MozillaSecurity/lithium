# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium Strategy tests"""

from pathlib import Path

import pytest

import lithium

pytestmark = pytest.mark.usefixtures("tmp_cwd")  # pylint: disable=invalid-name


def test_minimize(testcase_cls) -> None:
    """test that minimize strategy works"""
    test_path = Path("a.txt")

    class _Interesting:
        # pylint: disable=missing-function-docstring,no-self-use
        def init(self, condition_args):
            pass

        def interesting(self, *_):
            return b"o\n" in test_path.read_bytes()

        def cleanup(self, condition_args):
            pass

    obj = lithium.Lithium()
    obj.condition_script = _Interesting()
    obj.strategy = lithium.strategies.Minimize()
    test_path.write_bytes(b"x\n\nx\nx\no\nx\nx\nx\n")
    obj.testcase = testcase_cls()
    obj.testcase.load(test_path)
    assert obj.run() == 0
    assert test_path.read_bytes() == b"o\n"


def test_minimize_around(testcase_cls) -> None:
    """test that minimize around strategy works"""
    test_path = Path("a.txt")

    class _Interesting:
        # pylint: disable=missing-function-docstring,no-self-use
        def init(self, condition_args):
            pass

        def interesting(self, *_):
            data = test_path.read_bytes()
            return b"o\n" in data and len(set(data.split(b"o\n"))) == 1

        def cleanup(self, condition_args):
            pass

    obj = lithium.Lithium()
    obj.condition_script = _Interesting()
    obj.strategy = lithium.strategies.MinimizeSurroundingPairs()
    test_path.write_bytes(b"x\nx\nx\no\nx\nx\nx\n")
    obj.testcase = testcase_cls()
    obj.testcase.load(test_path)
    assert obj.run() == 0
    assert test_path.read_bytes() == b"o\n"


def test_minimize_balanced(testcase_cls) -> None:
    """test that minimize balanced strategy works"""
    test_path = Path("a.txt")

    class _Interesting:
        # pylint: disable=missing-function-docstring,no-self-use
        def init(self, condition_args):
            pass

        def interesting(self, *_):
            data = test_path.read_bytes()
            if b"o\n" in data:
                head, tail = data.split(b"o\n")
                return (
                    (head.count(b"{") == tail.count(b"}"))
                    and (head.count(b"(") == tail.count(b")"))
                    and (head.count(b"[") == tail.count(b"]"))
                )
            return False

        def cleanup(self, condition_args):
            pass

    obj = lithium.Lithium()
    obj.condition_script = _Interesting()
    obj.strategy = lithium.strategies.MinimizeBalancedPairs()
    test_path.write_bytes(b"[\n[\nxxx{\no\n}\n]\n]\n")
    obj.testcase = testcase_cls()
    obj.testcase.load(test_path)
    assert obj.run() == 0
    assert test_path.read_bytes() == b"o\n"


def test_replace_properties(testcase_cls) -> None:
    """test that replace properties strategy works"""
    original = (
        # original: this.list, prototype.push, prototype.last
        b"function Foo() {\n  this.list = [];\n}\n"
        b"Foo.prototype.push = function(a) {\n  this.list.push(a);\n}\n"
        b"Foo.prototype.last = function() {\n  return this.list.pop();\n}\n"
    )
    expected = (
        # reduced:       list,           push,           last
        b"function Foo() {\n  list = [];\n}\n"
        b"push = function(a) {\n  list.push(a);\n}\n"
        b"last = function() {\n  return list.pop();\n}\n"
    )
    valid_reductions = {
        original,
        #           this.list, prototype.push,           last
        b"function Foo() {\n  this.list = [];\n}\n"
        b"Foo.prototype.push = function(a) {\n  this.list.push(a);\n}\n"
        b"last = function() {\n  return this.list.pop();\n}\n",
        #           this.list,           push, prototype.last
        b"function Foo() {\n  this.list = [];\n}\n"
        b"push = function(a) {\n  this.list.push(a);\n}\n"
        b"Foo.prototype.last = function() {\n  return this.list.pop();\n}\n",
        #           this.list,           push,           last
        b"function Foo() {\n  this.list = [];\n}\n"
        b"push = function(a) {\n  this.list.push(a);\n}\n"
        b"last = function() {\n  return this.list.pop();\n}\n",
        #                list, prototype.push, prototype.last
        b"function Foo() {\n  list = [];\n}\n"
        b"Foo.prototype.push = function(a) {\n  list.push(a);\n}\n"
        b"Foo.prototype.last = function() {\n  return list.pop();\n}\n",
        #                list, prototype.push,           last
        b"function Foo() {\n  list = [];\n}\n"
        b"Foo.prototype.push = function(a) {\n  list.push(a);\n}\n"
        b"last = function() {\n  return list.pop();\n}\n",
        #                list,           push, prototype.last
        b"function Foo() {\n  list = [];\n}\n"
        b"push = function(a) {\n  list.push(a);\n}\n"
        b"Foo.prototype.last = function() {\n  return list.pop();\n}\n",
        expected,
    }
    test_path = Path("a.txt")

    class _Interesting:
        # pylint: disable=missing-function-docstring,no-self-use
        def init(self, condition_args):
            pass

        def interesting(self, *_):
            return test_path.read_bytes() in valid_reductions

        def cleanup(self, condition_args):
            pass

    obj = lithium.Lithium()
    test_path.write_bytes(original)
    obj.condition_script = _Interesting()
    obj.strategy = lithium.strategies.ReplacePropertiesByGlobals()
    obj.testcase = testcase_cls()
    obj.testcase.load(test_path)
    is_char = testcase_cls is lithium.testcases.TestcaseChar
    assert obj.run() == int(is_char)
    data = test_path.read_bytes()
    if is_char:
        # Char doesn't give this strategy enough to work with
        assert data == original
    else:
        assert data == expected


def test_replace_arguments(testcase_cls) -> None:
    """test that replace arguments strategy works"""
    original = b"function foo(a,b) {\n  list = a + b;\n}\nfoo(2,3)\n"
    expected = b"function foo() {\n  list = a + b;\n}\na = 2;\nb = 3;\nfoo()\n"
    valid_reductions = {
        original,
        b"function foo(a) {\n  list = a + b;\n}\nb = 3;\nfoo(2)\n",
        b"function foo(a) {\n  list = a + b;\n}\nb = 3;\nfoo(2,3)\n",
        b"function foo(b) {\n  list = a + b;\n}\na = 2;\nfoo(3)\n",
        b"function foo() {\n  list = a + b;\n}\na = 2;\nb = 3;\nfoo(2,3)\n",
        expected,
    }
    test_path = Path("a.txt")

    class _Interesting:
        # pylint: disable=missing-function-docstring,no-self-use
        def init(self, condition_args) -> None:
            pass

        def interesting(self, *_):
            return test_path.read_bytes() in valid_reductions

        def cleanup(self, condition_args) -> None:
            pass

    obj = lithium.Lithium()
    obj.condition_script = _Interesting()
    obj.strategy = lithium.strategies.ReplaceArgumentsByGlobals()
    test_path.write_bytes(original)
    obj.testcase = testcase_cls()
    obj.testcase.load(test_path)
    is_char = testcase_cls is lithium.testcases.TestcaseChar
    assert obj.run() == int(is_char)
    data = test_path.read_bytes()
    if is_char:
        # Char doesn't give this strategy enough to work with
        assert data == original
    else:
        assert data == expected


@pytest.mark.parametrize(
    "test_type, test_count, expected",
    [
        ("NEEDS_BRACE", 11, b"xxx{ }\n"),
        ("NO_BRACE", 13, b"o\n"),
    ],
)
def test_minimize_collapse_braces(test_type, test_count, expected) -> None:
    """test that collapse-braces strategy eliminates empty braces"""
    test_path = Path("a.txt")

    class _Interesting:
        # pylint: disable=missing-function-docstring,no-self-use
        def init(self, condition_args) -> None:
            pass

        def interesting(self, condition_args, *_):
            data = test_path.read_bytes()
            if condition_args == "NEEDS_BRACE":
                return data.count(b"{") == 1 and data.count(b"{") == data.count(b"}")

            if condition_args == "NO_BRACE":
                if b"o\n" in data:
                    return data.count(b"{") == data.count(b"}")

            return False

        def cleanup(self, condition_args) -> None:
            pass

    # CollapseEmptyBraces only applies to line-based reduction
    obj = lithium.Lithium()
    obj.condition_script = _Interesting()
    obj.condition_args = test_type
    obj.strategy = lithium.strategies.CollapseEmptyBraces()
    test_path.write_bytes(b"x\nxxx{\nx\n}\no\n")
    obj.testcase = lithium.testcases.TestcaseLine()
    obj.testcase.load(test_path)
    assert obj.run() == 0
    assert test_path.read_bytes() == expected
    assert obj.test_count == test_count


def test_minimize_reducible() -> None:
    """test that minimize works around non-reducible parts in the testcase"""
    test_path = Path("a.txt")

    class _Interesting:
        # pylint: disable=missing-function-docstring,no-self-use
        def init(self, condition_args) -> None:
            pass

        def interesting(self, *_):
            return b"o\n" in test_path.read_bytes()

        def cleanup(self, condition_args) -> None:
            pass

    obj = lithium.Lithium()
    obj.condition_script = _Interesting()
    obj.strategy = lithium.strategies.Minimize()
    test_path.write_bytes(b"x\n\nx\nx\no\nx\nx\nx\n")
    obj.testcase = lithium.testcases.TestcaseLine()
    obj.testcase.load(test_path)
    obj.testcase.reducible[0] = False
    assert obj.run() == 0
    assert test_path.read_bytes() == b"x\no\n"

    test_path.write_bytes(b"x\n\nx\nx\no\nx\nx\nx\n")
    obj.testcase = lithium.testcases.TestcaseLine()
    obj.testcase.load(test_path)
    obj.testcase.reducible[-1] = False
    assert obj.run() == 0
    assert test_path.read_bytes() == b"o\nx\n"
