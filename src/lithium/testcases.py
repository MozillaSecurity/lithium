# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium Testcase definitions.

A testcase is a file to be reduced, split in a certain way (eg. bytes, lines).
"""

import abc
import argparse
import logging
import os.path
import re
from pathlib import Path
from typing import List, Optional, Pattern, Tuple, Union

from .util import LithiumError

DEFAULT = "line"
LOG = logging.getLogger(__name__)


class Testcase(abc.ABC):
    """Lithium testcase base class."""

    atom: str
    """description of the units this testcase splits into"""

    def __init__(self) -> None:
        self.before: bytes = b""
        self.after: bytes = b""
        self.parts: List[bytes] = []
        # bool array with same length as `parts`
        # parts with a matchine `False` in `reducible` should
        # not be removed by the Strategy
        self.reducible: List[bool] = []
        self.filename: Optional[str] = None
        self.extension: Optional[str] = None

    def __len__(self) -> int:
        """Length of the testcase in terms of parts to be reduced.

        Returns:
            length of parts
        """
        return len(self.parts) - self.reducible.count(False)

    def _slice_xlat(
        self, start: Optional[int] = None, stop: Optional[int] = None
    ) -> Tuple[int, int]:
        # translate slice bounds within `[0, len(self))` (excluding non-reducible parts)
        # to bounds within `self.parts`
        len_self = len(self)

        def _clamp(bound: Optional[int], default: int) -> int:
            if bound is None:
                return default
            if bound < 0:
                return max(len_self + bound, 0)
            if bound > len_self:
                return len_self
            return bound

        start = _clamp(start, 0)
        stop = _clamp(stop, len_self)

        opts = [i for i in range(len(self.parts)) if self.reducible[i]]
        opts = [0] + opts[1:] + [len(self.parts)]

        return opts[start], opts[stop]

    def rmslice(self, start: int, stop: int) -> None:
        """Remove a slice of the testcase between `self.parts[start:stop]`, preserving
        non-reducible parts.

        Slice indices are between 0 and len(self), which may not be = len(self.parts)
        if any parts are marked non-reducible.

        Args:
            start: Slice start index
            stop: Slice stop index
        """
        start, stop = self._slice_xlat(start, stop)
        keep = [
            x
            for i, x in enumerate(self.parts[start:stop])
            if not self.reducible[start + i]
        ]
        self.parts = self.parts[:start] + keep + self.parts[stop:]
        self.reducible = (
            self.reducible[:start] + ([False] * len(keep)) + self.reducible[stop:]
        )

    def copy(self) -> "Testcase":
        """Duplicate the current object.

        Returns:
            type(self): A new object with the same type & contents of the original.
        """
        new = type(self)()
        new.before = self.before
        new.after = self.after
        new.parts = self.parts[:]
        new.reducible = self.reducible[:]
        new.filename = self.filename
        new.extension = self.extension
        return new

    def load(self, path: Union[Path, str]) -> None:
        """Load and split a testcase from disk.

        Args:
            path: Location on disk of testcase to read.

        Raises:
            LithiumError: DDBEGIN/DDEND token mismatch.
        """
        self.__init__()  # type: ignore[misc]
        self.filename = str(path)
        self.extension = os.path.splitext(self.filename)[1]

        with open(self.filename, "rb") as fileobj:
            text = fileobj.read().decode("utf-8", errors="surrogateescape")

            lines = [
                line.encode("utf-8", errors="surrogateescape")
                for line in text.splitlines(keepends=True)
            ]

        before = []
        while lines:
            line = lines.pop(0)
            before.append(line)
            if line.find(b"DDBEGIN") != -1:
                self.before = b"".join(before)
                del before
                break
            if line.find(b"DDEND") != -1:
                raise LithiumError(
                    "The testcase (%s) has a line containing 'DDEND' "
                    "without a line containing 'DDBEGIN' before it." % (self.filename,)
                )
        else:
            # no DDBEGIN/END, `before` contains the whole testcase
            self.split_parts(b"".join(before))
            return

        between = []
        while lines:
            line = lines.pop(0)
            if line.find(b"DDEND") != -1:
                self.after = line + b"".join(lines)
                break

            between.append(line)
        else:
            raise LithiumError(
                "The testcase (%s) has a line containing 'DDBEGIN' "
                "but no line containing 'DDEND'." % (self.filename,)
            )
        self.split_parts(b"".join(between))

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser) -> None:
        """Add any testcase specific arguments.

        Args:
            parser: argparse object to add arguments to.
        """

    def handle_args(self, args: argparse.Namespace) -> None:
        """Handle arguments after they have been parsed.

        Args:
            args: parsed argparse arguments.
        """

    @abc.abstractmethod
    def split_parts(self, data: bytes) -> None:
        """Should take testcase data and update `self.parts`.

        Args:
            data: Input read from the testcase file
                  (between DDBEGIN/END, if present).
        """

    def dump(self, path: Optional[Union[Path, str]] = None) -> None:
        """Write the testcase to the filesystem.

        Args:
            path: Output path (default: self.filename)
        """
        if path is None:
            assert self.filename is not None
            path = self.filename
        else:
            path = str(path)
        with open(path, "wb") as fileobj:
            fileobj.write(self.before)
            fileobj.writelines(self.parts)
            fileobj.write(self.after)


class TestcaseLine(Testcase):
    """Testcase file split by lines."""

    atom = "line"
    args = ("-l", "--lines")
    arg_help = "Treat the file as a sequence of lines."

    def split_parts(self, data: bytes) -> None:
        """Take input data and add lines to `parts` to be reduced.

        Args:
            data: Input data read from the testcase file.
        """
        orig = len(self.parts)
        self.parts.extend(
            line.encode("utf-8", errors="surrogateescape")
            for line in data.decode("utf-8", errors="surrogateescape").splitlines(
                keepends=True
            )
        )
        added = len(self.parts) - orig
        self.reducible.extend([True] * added)


class TestcaseChar(Testcase):
    """Testcase file split by bytes."""

    atom = "char"
    args = ("-c", "--char")
    arg_help = "Treat the file as a sequence of bytes."

    def load(self, path: Union[Path, str]) -> None:
        super().load(path)
        if (self.before or self.after) and self.parts:
            # Move the line break at the end of the last line out of the reducible
            # part so the "DDEND" line doesn't get combined with another line.
            self.parts.pop()
            self.reducible.pop()
            self.after = b"\n" + self.after

    def split_parts(self, data: bytes) -> None:
        orig = len(self.parts)
        self.parts.extend(data[i : i + 1] for i in range(len(data)))
        added = len(self.parts) - orig
        self.reducible.extend([True] * added)


class TestcaseJsStr(Testcase):
    """Testcase type for splitting JS strings byte-wise.

    Escapes are also kept together and treated as a single token for reduction.
    ref: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference
        /Global_Objects/String#Escape_notation
    """

    atom = "jsstr char"
    args = ("-j", "--js")
    arg_help = (
        "Same as --char but only operate within JS strings, keeping escapes intact."
    )

    def split_parts(self, data: bytes) -> None:
        instr = None
        chars: List[int] = []

        while True:
            last = 0
            while True:
                if instr:
                    match = re.match(
                        br"(\\u[0-9A-Fa-f]{4}|\\x[0-9A-Fa-f]{2}|"
                        br"\\u\{[0-9A-Fa-f]+\}|\\.|.)",
                        data[last:],
                        re.DOTALL,
                    )
                    if not match:
                        break
                    chars.append(len(self.parts))
                    if match.group(0) == instr:
                        instr = None
                        chars.pop()
                else:
                    match = re.search(br"""['"]""", data[last:])
                    if not match:
                        break
                    instr = match.group(0)
                self.parts.append(data[last : last + match.end(0)])
                last += match.end(0)

            if last != len(data):
                self.parts.append(data[last:])

            if instr is None:
                break

            # we hit EOF while looking for end of string, we need to rewind to the state
            # before we matched on that quote character and try again.

            idx = None
            for idx in reversed(range(len(self.parts))):
                if self.parts[idx].endswith(instr) and idx not in chars:
                    break
            else:
                raise RuntimeError("error while backtracking from unmatched " + instr)
            self.parts, data = self.parts[: idx + 1], b"".join(self.parts[idx + 1 :])
            chars = [c for c in chars if c < idx]
            instr = None

        # beginning and end are special because we can put them in
        # self.before/self.after
        if chars:
            # merge everything before first char (pre chars[0]) into self.before
            offset = chars[0]
            if offset:
                header, self.parts = b"".join(self.parts[:offset]), self.parts[offset:]
                self.before = self.before + header
                # update chars which is a list of offsets into self.parts
                chars = [c - offset for c in chars]

            # merge everything after last char (post chars[-1]) into self.after
            offset = chars[-1] + 1
            if offset < len(self.parts):
                self.parts, footer = self.parts[:offset], b"".join(self.parts[offset:])
                self.after = footer + self.after

        # now scan for chars with a gap > 2 between, which means we can merge
        # the goal is to take a string like this:
        #   parts = [a x x x b c]
        #   chars = [0       4 5]
        # and merge it into this:
        #   parts = [a xxx b c]
        #   chars = [0     2 3]
        for i in range(len(chars) - 1):
            char1, char2 = chars[i], chars[i + 1]
            if (char2 - char1) > 2:
                self.parts[char1 + 1 : char2] = [
                    b"".join(self.parts[char1 + 1 : char2])
                ]
                offset = char2 - char1 - 2  # num of parts we eliminated
                chars[i + 1 :] = [c - offset for c in chars[i + 1 :]]

        # default to everything non-reducible
        # mark every char index as reducible, so it can be removed
        self.reducible = [False] * len(self.parts)
        for idx in chars:
            self.reducible[idx] = True


class TestcaseSymbol(Testcase):
    """Testcase type for splitting a file before/after a set of delimiters."""

    atom = "symbol-delimiter"
    DEFAULT_CUT_AFTER = b"?=;{[\n"
    DEFAULT_CUT_BEFORE = b"]}:"
    args = ("-s", "--symbol")
    arg_help = (
        "Treat the file as a sequence of strings separated by tokens. "
        "The characters by which the strings are delimited are defined by "
        "the --cut-before, and --cut-after options."
    )

    def __init__(self) -> None:
        super().__init__()
        self._cutter: Optional[Pattern[bytes]] = None
        self.set_cut_chars(self.DEFAULT_CUT_BEFORE, self.DEFAULT_CUT_AFTER)

    def set_cut_chars(self, before: bytes, after: bytes) -> None:
        """Set the bytes used to delimit slice points.

        Args:
            before: Split file before these delimiters.
            after: Split file after these delimiters.
        """
        self._cutter = re.compile(
            b"["
            + before
            + b"]?"
            + b"[^"
            + before
            + after
            + b"]*"
            + b"(?:["
            + after
            + b"]|$|(?=["
            + before
            + b"]))"
        )

    def split_parts(self, data: bytes) -> None:
        assert self._cutter is not None
        for statement in self._cutter.finditer(data):
            if statement.group(0):
                self.parts.append(statement.group(0))
                self.reducible.append(True)

    def handle_args(self, args: argparse.Namespace) -> None:
        self.set_cut_chars(args.cut_before, args.cut_after)

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        grp_add = parser.add_argument_group(
            description="Additional options for the symbol-delimiter testcase type."
        )
        grp_add.add_argument(
            "--cut-before",
            default=cls.DEFAULT_CUT_BEFORE,
            help="See --symbol. default: " + cls.DEFAULT_CUT_BEFORE.decode("ascii"),
        )
        grp_add.add_argument(
            "--cut-after",
            default=cls.DEFAULT_CUT_AFTER,
            help="See --symbol. default: " + cls.DEFAULT_CUT_AFTER.decode("ascii"),
        )


class TestcaseAttrs(Testcase):
    """Testcase file split by anything that looks like an XML attribute."""

    atom = "attributes"
    args = ("-a", "--attrs")
    arg_help = "Delimit a file by XML attributes."
    TAG_PATTERN = br"<\s*[A-Za-z][A-Za-z-]*"
    ATTR_PATTERN = br"((\s+|^)[A-Za-z][A-Za-z0-9:-]*(=|>|\s)|\s*>)"

    def split_parts(self, data: bytes) -> None:
        in_tag = False
        while data:
            if in_tag:
                # we're in what looks like an element definition `<tag ...`
                # look for attributes, or the end `>`
                match = re.match(self.ATTR_PATTERN, data)

                if match is None:
                    # before bailing out of the tag, try consuming up to the next space
                    # and resuming the search
                    match = re.search(self.ATTR_PATTERN, data, flags=re.MULTILINE)
                    if match is not None and match.group(0).strip() != b">":
                        LOG.debug("skipping unrecognized data (%r)", match)
                        self.parts.append(data[: match.start(0)])
                        self.reducible.append(False)
                        data = data[match.start(0) :]
                        continue

                if match is None or match.group(0).strip() == b">":
                    in_tag = False
                    LOG.debug(
                        "no attribute found (%r) in %r..., looking for other tags",
                        match,
                        data[:20],
                    )
                    if match is not None:
                        self.parts.append(data[: match.end(0)])
                        self.reducible.append(False)
                        data = data[match.end(0) :]
                    continue

                # got an attribute
                if not match.group(0).endswith(b"="):
                    # value-less attribute, accept and continue
                    #
                    # only consume up to `match.end()-1` because we don't want the
                    # `\s` or `>` that occurred after the attribute. we need to match
                    # that for the next attribute / element end
                    LOG.debug("value-less attribute")
                    self.parts.append(data[: match.end(0) - 1])
                    self.reducible.append(True)
                    data = data[match.end(0) - 1 :]
                    continue
                # attribute has a value, need to find it's end
                attr_parts = [match.group(0)]
                data = data[match.end(0) :]
                if data[0:1] in {b"'", b'"'}:
                    # quote delimited string value, look for the end quote
                    attr_parts.append(data[0:1])
                    data = data[1:]
                    end_match = re.search(attr_parts[-1], data)
                    incl_end = True
                else:
                    end_match = re.search(br"(\s|>)", data)
                    incl_end = False
                if end_match is None:
                    # EOF looking for end quote
                    data = b"".join(attr_parts) + data
                    LOG.debug("EOF looking for attr end quote")
                    in_tag = False
                    continue
                end = end_match.end(0)
                if not incl_end:
                    end -= 1
                attr_parts.append(data[:end])
                data = data[end:]
                self.parts.append(b"".join(attr_parts))
                self.reducible.append(True)
                LOG.debug("found attribute: %r", self.parts[-1])
            else:
                match = re.search(self.TAG_PATTERN, data)
                if match is None:
                    break
                LOG.debug("entering tag: %s", match.group(0))
                in_tag = True
                self.parts.append(data[: match.end(0)])
                self.reducible.append(False)
                data = data[match.end(0) :]
        if data:
            LOG.debug("remaining data: %s", match and match.group(0))
            self.parts.append(data)
            self.reducible.append(False)
