# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium Testcase definitions.

A testcase is a file to be reduced, split in a certain way (eg. bytes, lines).
"""

import abc
import os.path
import re

from .util import LithiumError

DEFAULT = "line"


class Testcase(abc.ABC):
    """Lithium testcase base class."""

    def __init__(self):
        self.before = b""
        self.after = b""
        self.parts = []
        self.filename = None
        self.extension = None

    def __len__(self):
        """Length of the testcase in terms of parts to be reduced.

        Returns:
            int: length of parts
        """
        return len(self.parts)

    def copy(self):
        """Duplicate the current object.

        Returns:
            type(self): A new object with the same type & contents of the original.
        """
        new = type(self)()
        new.before = self.before
        new.after = self.after
        new.parts = self.parts[:]
        new.filename = self.filename
        new.extension = self.extension
        return new

    def load(self, path, state=None):
        """Load and split a testcase from disk.

        Args:
            path (Path or str): Location on disk of testcase to read.
            state (any): optional parsing state passed through to `split_parts()`

        Raises:
            LithiumError: DDBEGIN/DDEND token mismatch.
        """
        self.__init__()
        self.filename = str(path)
        self.extension = os.path.splitext(self.filename)[1]

        with open(self.filename, "rb") as fileobj:
            before = []
            for line in fileobj:
                before.append(line)
                if line.find(b"DDBEGIN") != -1:
                    self.before = b"".join(before)
                    del before
                    break
                if line.find(b"DDEND") != -1:
                    raise LithiumError(
                        "The testcase (%s) has a line containing 'DDEND' "
                        "without a line containing 'DDBEGIN' before it."
                        % (self.filename,)
                    )
            else:
                # no DDBEGIN/END, `before` contains the whole testcase
                for line in before:
                    self.parts.extend(self.split_parts(line, state=state))
                return

            for line in fileobj:
                if line.find(b"DDEND") != -1:
                    self.after = line + fileobj.read()
                    break

                self.parts.extend(self.split_parts(line, state=state))
            else:
                raise LithiumError(
                    "The testcase (%s) has a line containing 'DDBEGIN' "
                    "but no line containing 'DDEND'." % (self.filename,)
                )

    @staticmethod
    def add_arguments(parser):
        """Add any testcase specific arguments.

        Args:
            parser (ArgumentParser): argparse object to add arguments to.
        """

    def handle_args(self, args):
        """Handle arguments after they have been parsed.

        Args:
            args (argparse.Namespace): parsed argparse arguments.
        """

    @abc.abstractmethod
    def split_parts(self, line, state=None):
        """Should take a line of input and yield parts.

        Args:
            line (bytes): One line of input read from the testcase file.
            state (any): optional parsing state passed from `load()`

        Yields:
            bytes: parts to be reduced
        """

    def dump(self, path=None):
        """Write the testcase to the filesystem.

        Args:
            path (str or Path, optional): Output path (default: self.filename)
        """
        if path is None:
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

    def split_parts(self, line, state=None):
        """Take a line of input and yield lines to be reduced.

        Args:
            line (bytes): One line of input read from the testcase file.

        Yields:
            bytes: lines to be reduced
        """
        yield line


class TestcaseChar(Testcase):
    """Testcase file split by bytes."""

    atom = "char"
    args = ("-c", "--char")
    arg_help = "Treat the file as a sequence of bytes."

    def load(self, path, state=None):
        super().load(path)
        if (self.before or self.after) and self.parts:
            # Move the line break at the end of the last line out of the reducible
            # part so the "DDEND" line doesn't get combined with another line.
            self.parts.pop()
            self.after = b"\n" + self.after

    def split_parts(self, line, state=None):
        for char in line:
            yield bytes((char,))


class TestcaseJsStr(Testcase):
    """Testcase type for splitting JS strings byte-wise.

    Data between JS string contents (including the string quotes themselves!) will be a
    single token for reduction.

    Escapes are also kept together and treated as a single token for reduction.
    ref: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference
        /Global_Objects/String#Escape_notation
    """

    atom = "jsstr char"
    args = ("-j", "--js")
    arg_help = (
        "Same as --char but only operate within JS strings, keeping escapes intact."
    )

    def load(self, path, state=None):
        state = {
            "instr": None,
            "chars": [],
        }

        super().load(path, state=state)

        # if we hit EOF while looking for end of string, we need to rewind to the state
        # before we matched on that quote character and try again.
        while state["instr"] is not None:
            idx = None
            for idx in reversed(range(len(self))):
                if (
                    self.parts[idx].endswith(state["instr"])
                    and idx not in state["chars"]
                ):
                    break
            else:
                raise RuntimeError(
                    "error while backtracking from unmatched " + state["instr"]
                )
            self.parts, rest = self.parts[: idx + 1], b"".join(self.parts[idx + 1 :])
            state["chars"] = [c for c in state["chars"] if c < idx]
            state["instr"] = None
            self.parts.extend(self.split_parts(rest, state=state))

        # chars is a list of all the indices in self.parts which are chars
        # merge all the non-chars since this was parsed line-wise

        chars = state.pop("chars")

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

    def split_parts(self, line, state=None):
        last = 0
        while True:
            if state["instr"]:
                match = re.match(
                    br"(\\u[0-9A-Fa-f]{4}|\\x[0-9A-Fa-f]{2}|\\u\{[0-9A-Fa-f]+\}|\\.|.)",
                    line[last:],
                    re.DOTALL,
                )
                if not match:
                    break
                state["chars"].append(len(self.parts))
                if match.group(0) == state["instr"]:
                    state["instr"] = None
                    state["chars"].pop()
            else:
                match = re.search(br"""['"]""", line[last:])
                if not match:
                    break
                state["instr"] = match.group(0)
            yield line[last : last + match.end(0)]
            last += match.end(0)
        if last != len(line):
            yield line[last:]


class TestcaseSymbol(Testcase):
    """Testcase type for splitting a file before/after a set of delimiters."""

    atom = "symbol-delimiter"
    DEFAULT_CUT_AFTER = b"?=;{["
    DEFAULT_CUT_BEFORE = b"]}:"
    args = ("-s", "--symbol")
    arg_help = (
        "Treat the file as a sequence of strings separated by tokens. "
        "The characters by which the strings are delimited are defined by "
        "the --cut-before, and --cut-after options."
    )

    def __init__(self):
        super().__init__()
        self._cutter = None
        self.set_cut_chars(self.DEFAULT_CUT_BEFORE, self.DEFAULT_CUT_AFTER)

    def set_cut_chars(self, before, after):
        """Set the bytes used to delimit slice points.

        Args:
            before (bytes): Split file before these delimiters.
            after (bytes): Split file after these delimiters.
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

    def split_parts(self, line, state=None):
        for statement in self._cutter.finditer(line):
            if statement.group(0):
                yield statement.group(0)

    def handle_args(self, args):
        self.set_cut_chars(args.cut_before, args.cut_after)

    @classmethod
    def add_arguments(cls, parser):
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
