# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium tests"""

import logging
import shutil
from pathlib import Path

import pytest

import lithium

LOG = logging.getLogger(__name__)
pytestmark = pytest.mark.usefixtures("tmp_cwd")  # pylint: disable=invalid-name


def test_executable():
    """test lithium main help call"""
    with pytest.raises(SystemExit, match="0"):
        lithium.Lithium().main(["-h"])


def test_class():
    """test that lithium works as a class"""
    lith = lithium.Lithium()
    with open("empty.txt", "w"):
        pass

    class _Interesting:
        # pylint: disable=missing-function-docstring
        init_called = False
        interesting_called = False
        cleanup_called = False

        def init(self, *_):
            self.init_called = True

        def interesting(self, *_):
            self.interesting_called = True
            return True

        def cleanup(self, *_):
            self.cleanup_called = True

    inter = _Interesting()
    lith.condition_script = inter
    lith.condition_args = ["empty.txt"]
    lith.strategy = lithium.strategies.CheckOnly()
    lith.testcase = lithium.testcases.TestcaseLine()
    lith.testcase.load("empty.txt")
    assert lith.run() == 0
    assert inter.init_called
    assert inter.interesting_called
    assert inter.cleanup_called


def test_empty(caplog):
    """test lithium with empty input"""
    lith = lithium.Lithium()
    with open("empty.txt", "w"):
        pass

    class _Interesting:
        # pylint: disable=missing-function-docstring,no-self-use
        def init(self, *_):
            pass

        def interesting(self, *_):
            raise RuntimeError("Not expected to be run")

        def cleanup(self, *_):
            pass

    lith.condition_script = _Interesting()
    lith.strategy = lithium.strategies.Minimize()
    lith.testcase = lithium.testcases.TestcaseLine()
    lith.testcase.load("empty.txt")
    caplog.clear()
    assert lith.run() == 0
    for record in caplog.records:
        if record.name == "lithium.strategies" and record.levelno == logging.INFO:
            if (
                "The file has 0 lines so there's nothing for Lithium to try to remove!"
                in record.getMessage()
            ):
                break
    else:
        raise RuntimeError("Missing log output")


@pytest.mark.parametrize("char", [(True, False)])
def test_arithmetic(examples_path, char):
    """test lithium arithmetic example"""
    path = examples_path / "arithmetic"
    shutil.copyfile(str(path / "11.txt"), "11.txt")
    args = [str(path / "product_divides.py"), "35", "11.txt"]
    if char:
        args = ["-c"] + args
    result = lithium.Lithium().main(args)
    assert result == 0
    assert Path("11.txt").read_text() == "2\n\n# DDBEGIN\n5\n7\n# DDEND\n\n2\n"
