# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium Testcase* tests"""

from pathlib import Path

import pytest

import lithium

pytestmark = pytest.mark.usefixtures("tmp_cwd")  # pylint: disable=invalid-name


def test_line():
    """Test simple line splitting"""
    test = lithium.testcases.TestcaseLine()
    test_path = Path("a.txt")
    test_path.write_bytes(b"hello")
    test.load(test_path)
    test_path.unlink()
    test.dump()
    assert test_path.read_bytes() == b"hello"
    assert test.filename == "a.txt"
    assert test.extension == ".txt"
    assert test.before == b""
    assert test.parts == [b"hello"]
    assert test.after == b""
    test.dump("b.txt")
    assert Path("b.txt").read_bytes() == b"hello"


def test_line_dd():
    """Test line splitting with DDBEGIN/END"""
    test = lithium.testcases.TestcaseLine()
    test_path = Path("a.txt")
    with test_path.open("wb") as testf:
        testf.write(b"pre\n")
        testf.write(b"DDBEGIN\n")
        testf.write(b"data\n")
        testf.write(b"2\n")
        testf.write(b"DDEND\n")
        testf.write(b"post\n")
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\n"
    assert test.parts, [b"data\n" == b"2\n"]
    assert test.after == b"DDEND\npost\n"


def test_char_dd():
    """Test char splitting with DDBEGIN/END"""
    test = lithium.testcases.TestcaseChar()
    test_path = Path("a.txt")
    with test_path.open("wb") as testf:
        testf.write(b"pre\n")
        testf.write(b"DDBEGIN\n")
        testf.write(b"data\n")
        testf.write(b"2\n")
        testf.write(b"DDEND\n")
        testf.write(b"post\n")
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\n"
    assert test.parts, [b"d", b"a", b"t", b"a", b"\n" == b"2"]
    assert test.after == b"\nDDEND\npost\n"


def test_jsstr_0():
    """Test that the TestcaseJsStr class splits JS strings properly 0"""
    test = lithium.testcases.TestcaseJsStr()
    test_path = Path("a.txt")
    with test_path.open("wb") as testf:
        testf.write(b"pre\n")
        testf.write(b"DDBEGIN\n")
        testf.write(b"data\n")
        testf.write(b"2\n")
        testf.write(b"'\\u{123}\"1\\x32\\023\n'\n")  # a str with some escapes
        testf.write(b'""\n')  # empty string
        testf.write(b'"\\u12345Xyz"\n')  # another str with the last escape format
        testf.write(b"Data\xFF\n")
        testf.write(b'"x\xFF" something\n')  # last str
        testf.write(b"DDEND\n")
        testf.write(b"post\n")
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\ndata\n2\n'"
    assert test.parts == [
        b"\\u{123}",
        b'"',
        b"1",
        b"\\x32",
        b"\\0",
        b"2",
        b"3",
        b"\n",  # first JS str
        b'\'\n""\n"',  # empty string contains no chars, included with in-between data
        b"\\u1234",
        b"5",
        b"X",
        b"y",
        b"z",  # next JS str
        b'"\nData\xFF\n"',
        b"x",
        b"\xFF",
    ]  # last JS str
    assert test.after == b'" something\nDDEND\npost\n'


def test_jsstr_1():
    """Test that the TestcaseJsStr class splits JS strings properly 1"""
    test = lithium.testcases.TestcaseJsStr()
    test_path = Path("a.txt")
    test_path.write_bytes(b"'xabcx'")
    test.load(test_path)
    assert test.before == b"'"
    assert test.parts == [b"x", b"a", b"b", b"c", b"x"]
    assert test.after == b"'"


def test_jsstr_2():
    """Test that the TestcaseJsStr class splits JS strings properly 2"""
    test = lithium.testcases.TestcaseJsStr()
    test_path = Path("a.txt")
    test_path.write_bytes(b"'x'abcx'")
    test.load(test_path)
    assert test.before == b"'"
    assert test.parts == [b"x"]
    assert test.after == b"'abcx'"


def test_jsstr_3():
    """Test that the TestcaseJsStr class splits JS strings properly 3"""
    test = lithium.testcases.TestcaseJsStr()
    test_path = Path("a.txt")
    test_path.write_bytes(b'\'x"abc"x')
    test.load(test_path)
    assert test.before == b"'x\""
    assert test.parts == [b"a", b"b", b"c"]
    assert test.after == b'"x'


def test_symbol_0():
    """Test symbol splitting 0"""
    test = lithium.testcases.TestcaseSymbol()
    test_path = Path("a.txt")
    with test_path.open("wb") as testf:
        testf.write(b"pre\n")
        testf.write(b"DDBEGIN\n")
        testf.write(b"d{a}ta\n")
        testf.write(b"2\n")
        testf.write(b"DDEND\n")
        testf.write(b"post\n")
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\n"
    assert test.parts, [b"d{", b"a", b"}ta\n" == b"2\n"]
    assert test.after == b"DDEND\npost\n"


def test_symbol_1():
    """Test symbol splitting 1"""
    test = lithium.testcases.TestcaseSymbol()
    test_path = Path("a.txt")
    with test_path.open("wb") as testf:
        testf.write(b"pre\n")
        testf.write(b"DDBEGIN\n")
        testf.write(b"{data\n")
        testf.write(b"2}\n}")
        testf.write(b"DDEND\n")
        testf.write(b"post\n")
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\n"
    assert test.parts, [b"{", b"data\n", b"2" == b"}\n"]
    assert test.after == b"}DDEND\npost\n"


@pytest.mark.parametrize(
    "data,error",
    [
        (b"DDEND\n", "'DDEND' without"),
        (b"DDBEGIN DDEND\n", "'DDBEGIN' but no"),
        (b"DDBEGIN DDEND\n", "'DDBEGIN' but no"),
        (b"DDEND DDBEGIN\n", "'DDBEGIN' but no"),
        (b"DDBEGIN\n", "'DDBEGIN' but no"),
    ],
)
def test_errors(data, error):
    """Test DDBEGIN/END errors"""
    test = lithium.testcases.TestcaseLine()
    test_path = Path("a.txt")
    test_path.write_bytes(data)
    with pytest.raises(
        lithium.LithiumError,
        match=r"^The testcase \(%s\) has a line containing %s" % (test_path, error),
    ):
        test.load(test_path)
