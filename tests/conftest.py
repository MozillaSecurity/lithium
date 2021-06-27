# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""lithium unittest fixtures"""

import argparse
import os
from pathlib import Path
from typing import Iterator

import pytest

import lithium


def pytest_addoption(parser: argparse.Namespace) -> None:
    """Add option to only lint and not run tests"""
    parser.addoption(
        "--lint-only",
        action="store_true",
        default=False,
        help="Only run linting checks",
    )


# pylint: disable=unused-argument
def pytest_collection_modifyitems(session, config, items) -> None:
    """Disable collection if any linters are specified, and --lint-only is given"""
    if config.getoption("--lint-only"):
        lint_items = []
        for linter in ["flake8", "pylint"]:
            if config.getoption("--" + linter):
                lint_items.extend(
                    [item for item in items if item.get_closest_marker(linter)]
                )
        items[:] = lint_items


@pytest.fixture(
    params=[
        lithium.testcases.TestcaseChar,
        lithium.testcases.TestcaseLine,
        lithium.testcases.TestcaseSymbol,
    ]
)
def testcase_cls(request):
    """Use char/line/symbol testcase type for a given test"""
    yield request.param


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Iterator[Path]:
    """Same as tmp_path, but chdir to the tmp folder too."""
    orig = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        yield tmp_path
    finally:
        os.chdir(orig)


@pytest.fixture
def examples_path() -> Iterator[Path]:
    """Path to the lithium examples folder"""
    yield Path(__file__).parent.parent / "src" / "lithium" / "docs" / "examples"
