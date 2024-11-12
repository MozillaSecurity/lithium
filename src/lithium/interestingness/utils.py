#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""This lets you import an interestingness test given a full path, or given just a
filename. (assuming it's in the current directory OR in the same directory as utils.py)
"""

import importlib
import logging
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Union


def file_contains_str(
    input_file: Union[Path, str],
    regex: bytes,
    verbose: bool = True,
) -> bool:
    """Helper function to check if file contains a given string

    Args:
        input_file: file to search
        regex: pattern to look for
        verbose: print matches to stdout

    Returns:
        if match was found
    """
    file_contents = Path(input_file).read_bytes()
    idx = file_contents.find(regex)
    if idx != -1:
        if verbose and regex != b"":
            # rather than print the whole file, print the lines containing the
            # match, up to the surrounding '\n'
            prev_nl = max(file_contents.rfind(b"\n", 0, idx + 1), 0)
            next_nl = idx + len(regex)
            if not regex.endswith(b"\n"):
                next_nl = max(file_contents.find(b"\n", idx + len(regex)), next_nl)
            match = file_contents[prev_nl:next_nl].decode("utf-8", errors="replace")
            print(f"[Found string in: {match!r}]", end=" ")
        return True
    return False


def file_contains_regex(
    input_file: Union[Path, str],
    regex: bytes,
    verbose: bool = True,
) -> tuple[bool, bytes]:
    """e.g. python -m lithium crashesat --timeout=30 \
      --regex '^#0\\s*0x.* in\\s*.*(?:\\n|\\r\\n?)#1\\s*' \
      ./js --fuzzing-safe --no-threads --ion-eager testcase.js
    Note that putting "^" and "$" together is unlikely to work.

    Args:
        input_file: file to search
        regex: pattern to look for
        verbose: print matches to stdout

    Returns:
        if match was found, and matched string
    """

    matched_str = b""
    found = False
    file_contents = Path(input_file).read_bytes()
    found_regex = re.search(regex, file_contents, flags=re.MULTILINE)
    if found_regex:
        matched_str = found_regex.group()
        if verbose and matched_str != b"":
            print(
                "[Found string in: '"
                + matched_str.decode("utf-8", errors="replace")
                + "']",
                end=" ",
            )
        found = True
    return found, matched_str


def rel_or_abs_import(module: str) -> ModuleType:
    """Import a module from anywhere.
    If a full path to module is given, try to import from there.
    If a relative path to module is given (module or module.py), try to import from
    current working directory or the lithium interestingness module.

    Args:
        module: the module name to try importing

    Returns:
        namespace: the module

    Raises:
        ImportError: if module cannot be imported
    """
    log = logging.getLogger("lithium")

    orig_arg = module
    path, module = os.path.split(module)
    if not module:
        # module arg ended in slash, module must be a directory?
        path, module = os.path.split(path)
    if module.endswith(".py"):
        module = module[:-3]
    if path:
        # full path given, try that
        sys.path.append(os.path.realpath(path))
    else:
        sys.path.append(os.path.realpath("."))
    try:
        return importlib.import_module(module)
    except ImportError:
        # only raise if path was given, otherwise we also try under 'interestingness'
        if path:
            log.error("Failed to import: %s", orig_arg)
            log.error("From: %s", __file__)
            raise
    finally:
        sys.path.pop()
    # if we have not returned or raised by now, the import was unsuccessful and module
    # was a name only also try to import from 'interestingness'
    try:
        return importlib.import_module(".interestingness." + module, package="lithium")
    except ImportError:
        log.error("Failed to import: .interestingness.%s", module)
        log.error("From: %s", __file__)
        raise
