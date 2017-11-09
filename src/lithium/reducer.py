#!/usr/bin/env python
# coding=utf-8
# pylint: disable=missing-docstring
# pylint: disable=too-many-lines
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import logging
import os
import re
import time

from .interestingness.utils import rel_or_abs_import

log = logging.getLogger("lithium")  # pylint: disable=invalid-name


class LithiumError(Exception):  # pylint: disable=missing-docstring
    pass


class Testcase(object):
    """Abstract testcase class.

    Implementers should define readTestcaseLine() and writeTestcase() methods.
    """

    def __init__(self):
        self.before = b""
        self.after = b""
        self.parts = []

        self.filename = None
        self.extension = None

    def copy(self):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
        new = type(self)()

        new.before = self.before
        new.after = self.after
        new.parts = self.parts[:]

        new.filename = self.filename
        new.extension = self.extension

        return new

    def readTestcase(self, filename):  # pylint: disable=invalid-name,missing-docstring
        hasDDSection = False  # pylint: disable=invalid-name

        self.__init__()
        self.filename = filename
        self.extension = os.path.splitext(self.filename)[1]

        with open(self.filename, "rb") as f:
            # Determine whether the f has a DDBEGIN..DDEND section.
            for line in f:
                if line.find(b"DDEND") != -1:
                    raise LithiumError("The testcase (%s) has a line containing 'DDEND' "
                                       "without a line containing 'DDBEGIN' before it." % self.filename)
                if line.find(b"DDBEGIN") != -1:
                    hasDDSection = True  # pylint: disable=invalid-name
                    break

            f.seek(0)

            if hasDDSection:
                # Reduce only the part of the file between 'DDBEGIN' and 'DDEND',
                # leaving the rest unchanged.
                # log.info("Testcase has a DD section")
                self.readTestcaseWithDDSection(f)
            else:
                # Reduce the entire file.
                # log.info("Testcase does not have a DD section")
                for line in f:
                    self.readTestcaseLine(line)

    def readTestcaseWithDDSection(self, f):  # pylint: disable=invalid-name,missing-docstring
        for line in f:
            self.before += line
            if line.find(b"DDBEGIN") != -1:
                break

        for line in f:
            if line.find(b"DDEND") != -1:
                self.after += line
                break
            self.readTestcaseLine(line)
        else:
            raise LithiumError("The testcase (%s) has a line containing 'DDBEGIN' but no line "
                               "containing 'DDEND'." % self.filename)

        for line in f:
            self.after += line

    def readTestcaseLine(self, line):  # pylint: disable=invalid-name,missing-docstring
        raise NotImplementedError()

    def writeTestcase(self, filename=None):  # pylint: disable=invalid-name,missing-docstring
        raise NotImplementedError()


class TestcaseLine(Testcase):  # pylint: disable=missing-docstring
    atom = "line"

    def readTestcaseLine(self, line):
        self.parts.append(line)

    def writeTestcase(self, filename=None):
        if filename is None:
            filename = self.filename
        with open(filename, "wb") as f:
            f.write(self.before)
            f.writelines(self.parts)
            f.write(self.after)


class TestcaseChar(TestcaseLine):  # pylint: disable=missing-docstring
    atom = "char"

    def readTestcaseWithDDSection(self, f):
        Testcase.readTestcaseWithDDSection(self, f)

        if self.parts:
            # Move the line break at the end of the last line out of the reducible
            # part so the "DDEND" line doesn't get combined with another line.
            self.parts.pop()
            self.after = b"\n" + self.after

    def readTestcaseLine(self, line):
        for i in range(len(line)):
            self.parts.append(line[i:i + 1])


class TestcaseJsStr(TestcaseChar):
    """Testcase type for splitting JS strings byte-wise.

    Data between JS string contents (including the string quotes themselves!) will be a single token for reduction.

    Escapes are also kept together and treated as a single token for reduction.
    ref: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String#Escape_notation
    """
    atom = "jsstr char"

    def readTestcaseWithDDSection(self, f):
        Testcase.readTestcaseWithDDSection(self, f)

    def readTestcase(self, filename):
        # these are temporary attributes used to track state in readTestcaseLine (called by super().readTestcase)
        # they are both deleted after the call below and not available in the instance normally
        self._instr = None  # pylint: disable=attribute-defined-outside-init
        self._chars = []  # pylint: disable=attribute-defined-outside-init

        super(TestcaseJsStr, self).readTestcase(filename)

        assert self._instr is None, "Unexpected EOF looking for end of string (%s)" % self._instr
        del self._instr

        # self._chars is a list of all the indices in self.parts which are chars
        # merge all the non-chars since this was parsed line-wise

        chars = self._chars
        del self._chars

        # beginning and end are special because we can put them in self.before/self.after
        if chars:
            off = -chars[0]
            if off:
                header, self.parts = b"".join(self.parts[:-off]), self.parts[-off:]
                self.before = self.before + header
            if chars[-1] != len(self.parts) + off:
                self.parts, footer = self.parts[:chars[-1] + 1 + off], b"".join(self.parts[chars[-1] + 1 + off:])
                self.after = footer + self.after

        # now scan for chars with a gap > 2 between, which means we can merge
        for char1, char2 in zip(chars, chars[1:]):
            if (char2 - char1) > 2:
                self.parts[off + char1 + 1:off + char2] = [b"".join(self.parts[off + char1 + 1:off + char2])]
                off += char1 - char2 + 2

    def readTestcaseLine(self, line):
        last = 0
        while True:
            if self._instr:
                match = re.match(br"(\\u[0-9A-Fa-f]{4}|\\x[0-9A-Fa-f]{2}|\\u\{[0-9A-Fa-f]+\}|\\.|.)", line[last:],
                                 re.DOTALL)
                if not match:
                    break
                self._chars.append(len(self.parts))
                if match.group(0) == self._instr:
                    self._instr = None  # pylint: disable=attribute-defined-outside-init
                    self._chars.pop()
            else:
                match = re.search(br"""['"]""", line[last:])
                if not match:
                    break
                self._instr = match.group(0)  # pylint: disable=attribute-defined-outside-init
            self.parts.append(line[last:last + match.end(0)])
            last += match.end(0)
        if last != len(line):
            self.parts.append(line[last:])


class TestcaseSymbol(TestcaseLine):  # pylint: disable=missing-docstring
    atom = "symbol-delimiter"
    DEFAULT_CUT_AFTER = b"?=;{["
    DEFAULT_CUT_BEFORE = b"]}:"

    def __init__(self):
        TestcaseLine.__init__(self)

        self.cutAfter = self.DEFAULT_CUT_AFTER  # pylint: disable=invalid-name
        self.cutBefore = self.DEFAULT_CUT_BEFORE  # pylint: disable=invalid-name

    def readTestcaseLine(self, line):
        cutter = (b"[" + self.cutBefore + b"]?" +
                  b"[^" + self.cutBefore + self.cutAfter + b"]*" +
                  b"(?:[" + self.cutAfter + b"]|$|(?=[" + self.cutBefore + b"]))")
        for statement in re.finditer(cutter, line):
            if statement.group(0):
                self.parts.append(statement.group(0))


class Strategy(object):
    """Abstract minimization strategy class

    Implementers should define a main() method which takes a testcase and calls the interesting callback repeatedly
    to minimize the testcase.
    """

    def addArgs(self, parser):  # pylint: disable=invalid-name,missing-docstring
        pass

    def processArgs(self, parser, args):  # pylint: disable=invalid-name,missing-docstring
        pass

    def main(self, testcase, interesting, tempFilename):  # pylint: disable=invalid-name,missing-docstring
        raise NotImplementedError()


class CheckOnly(Strategy):  # pylint: disable=missing-docstring
    name = "check-only"

    def main(self, testcase, interesting, tempFilename):  # pylint: disable=missing-return-doc,missing-return-type-doc
        r = interesting(testcase, writeIt=False)  # pylint: disable=invalid-name
        log.info("Lithium result: %s", ("interesting." if r else "not interesting."))
        return 0


class Minimize(Strategy):
    """    Main reduction algorithm

    This strategy attempts to remove chunks which might not be interesting
    code, but which can be removed independently of any other.  This happens
    frequently with values which are computed, but either after the execution,
    or never used to influenced the interesting part.

      a = compute();
      b = compute();   <-- !!!
      interesting(a);
      c = compute();   <-- !!!"""

    name = "minimize"

    def __init__(self):
        self.minimizeRepeat = "last"  # pylint: disable=invalid-name
        self.minimizeMin = 1  # pylint: disable=invalid-name
        self.minimizeMax = pow(2, 30)  # pylint: disable=invalid-name
        self.minimizeChunkStart = 0  # pylint: disable=invalid-name
        self.minimizeChunkSize = None  # pylint: disable=invalid-name
        self.minimizeRepeatFirstRound = False  # pylint: disable=invalid-name
        self.stopAfterTime = None  # pylint: disable=invalid-name

    def addArgs(self, parser):
        grp_add = parser.add_argument_group(description="Additional options for the %s strategy" % self.name)
        grp_add.add_argument(
            "--min", type=int,
            default=1,
            help="must be a power of two. default: 1")
        grp_add.add_argument(
            "--max", type=int,
            default=pow(2, 30),
            help="must be a power of two. default: about half of the file")
        grp_add.add_argument(
            "--repeat",
            default="last",
            choices=["always", "last", "never"],
            help="Whether to repeat a chunk size if chunks are removed. default: last")
        grp_add.add_argument(
            "--chunksize", type=int,
            default=None,
            help="Shortcut for repeat=never, min=n, max=n. chunk size must be a power of two.")
        grp_add.add_argument(
            "--chunkstart", type=int,
            default=0,
            help="For the first round only, start n chars/lines into the file. Best for max to divide n. "
                 "[Mostly intended for internal use]")
        grp_add.add_argument(
            "--repeatfirstround", action="store_true",
            help="Treat the first round as if it removed chunks; possibly repeat it. "
                 "[Mostly intended for internal use]")
        grp_add.add_argument(
            "--maxruntime", type=int,
            default=None,
            help="If reduction takes more than n seconds, stop (and print instructions for continuing).")

    def processArgs(self, parser, args):
        if args.chunksize:
            self.minimizeMin = args.chunksize
            self.minimizeMax = args.chunksize
            self.minimizeRepeat = "never"
        else:
            self.minimizeMin = args.min
            self.minimizeMax = args.max
            self.minimizeRepeat = args.repeat
        self.minimizeChunkStart = args.chunkstart
        self.minimizeRepeatFirstRound = args.repeatfirstround
        if args.maxruntime:
            self.stopAfterTime = time.time() + args.maxruntime
        if not isPowerOfTwo(self.minimizeMin) or not isPowerOfTwo(self.minimizeMax):
            parser.error("Min/Max must be powers of two.")

    def main(self, testcase, interesting, tempFilename):  # pylint: disable=missing-return-doc,missing-return-type-doc
        log.info("The original testcase has %s.", quantity(len(testcase.parts), testcase.atom))
        log.info("Checking that the original testcase is 'interesting'...")
        if not interesting(testcase, writeIt=False):
            log.info("Lithium result: the original testcase is not 'interesting'!")
            return 1

        if not testcase.parts:
            log.info("The file has %s so there's nothing for Lithium to try to remove!", quantity(0, testcase.atom))

        testcase.writeTestcase(tempFilename("original", False))

        origNumParts = len(testcase.parts)  # pylint: disable=invalid-name
        result, anySingle, testcase = self.run(testcase, interesting, tempFilename)  # pylint: disable=invalid-name

        testcase.writeTestcase()

        summaryHeader()

        if anySingle:
            log.info("  Removing any single %s from the final file makes it uninteresting!", testcase.atom)

        log.info("  Initial size: %s", quantity(origNumParts, testcase.atom))
        log.info("  Final size: %s", quantity(len(testcase.parts), testcase.atom))

        return result

    def run(self, testcase, interesting, tempFilename):  # pylint: disable=invalid-name,missing-docstring
        # pylint: disable=missing-return-doc,missing-return-type-doc
        # pylint: disable=invalid-name
        chunkSize = min(self.minimizeMax, largestPowerOfTwoSmallerThan(len(testcase.parts)))
        finalChunkSize = min(chunkSize, max(self.minimizeMin, 1))  # pylint: disable=invalid-name
        chunkStart = self.minimizeChunkStart  # pylint: disable=invalid-name
        anyChunksRemoved = self.minimizeRepeatFirstRound  # pylint: disable=invalid-name

        while True:
            if self.stopAfterTime and time.time() > self.stopAfterTime:
                # Not all switches will be copied!  Be sure to add --tempdir, --maxruntime if desired.
                # Not using shellify() here because of the strange requirements of bot.py's lithium-command.txt.
                log.info("Lithium result: please perform another pass using the same arguments")
                break

            if chunkStart >= len(testcase.parts):
                testcase.writeTestcase(tempFilename("did-round-%d" % chunkSize))
                last = (chunkSize <= finalChunkSize)
                empty = not testcase.parts
                log.info("")
                if not empty and anyChunksRemoved and (self.minimizeRepeat == "always" or
                                                       (self.minimizeRepeat == "last" and last)):
                    chunkStart = 0
                    log.info("Starting another round of chunk size %d", chunkSize)
                elif empty or last:
                    log.info("Lithium result: succeeded, reduced to: %s", quantity(len(testcase.parts), testcase.atom))
                    break
                else:
                    chunkStart = 0
                    while chunkSize > 1:  # smallest valid chunk size is 1
                        chunkSize >>= 1
                        # To avoid testing with an empty testcase (wasting cycles) only break when
                        # chunkSize is less than the number of testcase parts available.
                        if chunkSize < len(testcase.parts):
                            break
                    log.info("Reducing chunk size to %d", chunkSize)
                anyChunksRemoved = False

            chunkEnd = min(len(testcase.parts), chunkStart + chunkSize)
            description = "Removing a chunk of size %d starting at %d of %d" % (
                chunkSize, chunkStart, len(testcase.parts))
            testcaseSuggestion = testcase.copy()
            testcaseSuggestion.parts = testcaseSuggestion.parts[:chunkStart] + testcaseSuggestion.parts[chunkEnd:]
            if interesting(testcaseSuggestion):
                testcase = testcaseSuggestion
                log.info("%s was a successful reduction :)", description)
                anyChunksRemoved = True
                # leave chunkStart the same
            else:
                log.info("%s made the file 'uninteresting'.", description)
                chunkStart += chunkSize

        return 0, (chunkSize == 1 and not anyChunksRemoved and self.minimizeRepeat != "never"), testcase


class MinimizeSurroundingPairs(Minimize):
    """    This strategy attempts to remove pairs of chunks which might be surrounding
    interesting code, but which cannot be removed independently of the other.
    This happens frequently with patterns such as:

      a = 42;
      while (true) {
         b = foo(a);      <-- !!!
         interesting();
         a = bar(b);      <-- !!!
      }"""

    name = "minimize-around"

    def run(self, testcase, interesting, tempFilename):  # pylint: disable=missing-return-doc,missing-return-type-doc
        # pylint: disable=invalid-name
        chunkSize = min(self.minimizeMax, largestPowerOfTwoSmallerThan(len(testcase.parts)))
        finalChunkSize = max(self.minimizeMin, 1)  # pylint: disable=invalid-name

        while 1:
            anyChunksRemoved, testcase = self.tryRemovingChunks(chunkSize, testcase, interesting, tempFilename)

            last = (chunkSize <= finalChunkSize)

            if anyChunksRemoved and (self.minimizeRepeat == "always" or (self.minimizeRepeat == "last" and last)):
                # Repeat with the same chunk size
                pass
            elif last:
                # Done
                break
            else:
                # Continue with the next smaller chunk size
                chunkSize >>= 1

        return 0, (finalChunkSize == 1 and self.minimizeRepeat != "never"), testcase

    @staticmethod
    def list_rindex(l, p, e):  # pylint: disable=invalid-name,missing-docstring
        # pylint: disable=missing-return-doc,missing-return-type-doc
        if p < 0 or p > len(l):
            raise ValueError("%s is not in list" % e)
        for index, item in enumerate(reversed(l[:p])):
            if item == e:
                return p - index - 1
        raise ValueError("%s is not in list" % e)

    @staticmethod
    def list_nindex(l, p, e):  # pylint: disable=invalid-name,missing-docstring
        # pylint: disable=missing-return-doc,missing-return-type-doc
        if p + 1 >= len(l):
            raise ValueError("%s is not in list" % e)
        return l[(p + 1):].index(e) + (p + 1)

    def tryRemovingChunks(self, chunkSize, testcase, interesting, tempFilename):  # pylint: disable=invalid-name
        # pylint: disable=missing-param-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
        # pylint: disable=too-many-locals,too-many-statements
        """Make a single run through the testcase, trying to remove chunks of size chunkSize.

        Returns True iff any chunks were removed."""

        summary = ""

        chunksRemoved = 0  # pylint: disable=invalid-name
        atomsRemoved = 0  # pylint: disable=invalid-name

        atomsInitial = len(testcase.parts)  # pylint: disable=invalid-name
        numChunks = divideRoundingUp(len(testcase.parts), chunkSize)  # pylint: disable=invalid-name

        # Not enough chunks to remove surrounding blocks.
        if numChunks < 3:
            return False, testcase

        log.info("Starting a round with chunks of %s.", quantity(chunkSize, testcase.atom))

        summary = ["S" for _ in range(numChunks)]
        chunkStart = chunkSize  # pylint: disable=invalid-name
        beforeChunkIdx = 0  # pylint: disable=invalid-name
        keepChunkIdx = 1  # pylint: disable=invalid-name
        afterChunkIdx = 2  # pylint: disable=invalid-name

        try:
            while chunkStart + chunkSize < len(testcase.parts):
                chunkBefStart = max(0, chunkStart - chunkSize)  # pylint: disable=invalid-name
                chunkBefEnd = chunkStart  # pylint: disable=invalid-name
                chunkAftStart = min(len(testcase.parts), chunkStart + chunkSize)  # pylint: disable=invalid-name
                chunkAftEnd = min(len(testcase.parts), chunkAftStart + chunkSize)  # pylint: disable=invalid-name
                description = "chunk #%d & #%d of %d chunks of size %d" % (
                    beforeChunkIdx, afterChunkIdx, numChunks, chunkSize)

                testcaseSuggestion = testcase.copy()  # pylint: disable=invalid-name
                testcaseSuggestion.parts = (testcaseSuggestion.parts[:chunkBefStart] +
                                            testcaseSuggestion.parts[chunkBefEnd:chunkAftStart] +
                                            testcaseSuggestion.parts[chunkAftEnd:])
                if interesting(testcaseSuggestion):
                    testcase = testcaseSuggestion
                    log.info("Yay, reduced it by removing %s :)", description)
                    chunksRemoved += 2  # pylint: disable=invalid-name
                    atomsRemoved += (chunkBefEnd - chunkBefStart)  # pylint: disable=invalid-name
                    atomsRemoved += (chunkAftEnd - chunkAftStart)  # pylint: disable=invalid-name
                    summary[beforeChunkIdx] = "-"
                    summary[afterChunkIdx] = "-"
                    # The start is now sooner since we remove the chunk which was before this one.
                    chunkStart -= chunkSize  # pylint: disable=invalid-name
                    try:
                        # Try to keep removing surrounding chunks of the same part.
                        beforeChunkIdx = self.list_rindex(summary, keepChunkIdx, "S")  # pylint: disable=invalid-name
                    except ValueError:
                        # There is no more survinving block on the left-hand-side of
                        # the current chunk, shift everything by one surviving
                        # block. Any ValueError from here means that there is no
                        # longer enough chunk.
                        beforeChunkIdx = keepChunkIdx  # pylint: disable=invalid-name
                        keepChunkIdx = self.list_nindex(summary, keepChunkIdx, "S")  # pylint: disable=invalid-name
                        chunkStart += chunkSize  # pylint: disable=invalid-name
                else:
                    log.info("Removing %s made the file 'uninteresting'.", description)
                    # Shift chunk indexes, and seek the next surviving chunk. ValueError
                    # from here means that there is no longer enough chunks.
                    beforeChunkIdx = keepChunkIdx  # pylint: disable=invalid-name
                    keepChunkIdx = afterChunkIdx  # pylint: disable=invalid-name
                    chunkStart += chunkSize  # pylint: disable=invalid-name

                afterChunkIdx = self.list_nindex(summary, keepChunkIdx, "S")  # pylint: disable=invalid-name

        except ValueError:
            # This is a valid loop exit point.
            chunkStart = len(testcase.parts)  # pylint: disable=invalid-name

        atomsSurviving = atomsInitial - atomsRemoved  # pylint: disable=invalid-name
        printableSummary = " ".join(  # pylint: disable=invalid-name
            "".join(summary[(2 * i):min(2 * (i + 1), numChunks + 1)]) for i in range(numChunks // 2 + numChunks % 2))
        log.info("")
        log.info("Done with a round of chunk size %d!", chunkSize)
        log.info("%s survived; %s removed.",
                 quantity(summary.count("S"), "chunk"),
                 quantity(summary.count("-"), "chunk"))
        log.info("%s survived; %s removed.",
                 quantity(atomsSurviving, testcase.atom),
                 quantity(atomsRemoved, testcase.atom))
        log.info("Which chunks survived: %s", printableSummary)
        log.info("")

        testcase.writeTestcase(tempFilename("did-round-%d" % chunkSize))

        return bool(chunksRemoved), testcase


class MinimizeBalancedPairs(MinimizeSurroundingPairs):
    """    This strategy attempts to remove balanced chunks which might be surrounding
    interesting code, but which cannot be removed independently of the other.
    This happens frequently with patterns such as:

      ...;
      if (cond) {        <-- !!!
         ...;
         interesting();
         ...;
      }                  <-- !!!
      ...;

    The value of the condition might not be interesting, but in order to reach the
    interesting code we still have to compute it, and keep extra code alive."""

    name = "minimize-balanced"

    @staticmethod
    def list_fiveParts(lst, step, f, s, t):  # pylint: disable=invalid-name,missing-docstring
        # pylint: disable=missing-return-doc,missing-return-type-doc
        return (lst[:f], lst[f:s], lst[s:(s + step)], lst[(s + step):(t + step)], lst[(t + step):])

    def tryRemovingChunks(self, chunkSize, testcase, interesting, tempFilename):
        # pylint: disable=missing-param-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
        # pylint: disable=too-many-branches,too-complex,too-many-locals,too-many-statements
        """Make a single run through the testcase, trying to remove chunks of size chunkSize.

        Returns True iff any chunks were removed."""

        summary = ""

        chunksRemoved = 0  # pylint: disable=invalid-name
        atomsRemoved = 0  # pylint: disable=invalid-name

        atomsInitial = len(testcase.parts)  # pylint: disable=invalid-name
        numChunks = divideRoundingUp(len(testcase.parts), chunkSize)  # pylint: disable=invalid-name

        # Not enough chunks to remove surrounding blocks.
        if numChunks < 2:
            return False, testcase

        log.info("Starting a round with chunks of %s.", quantity(chunkSize, testcase.atom))

        summary = ["S" for i in range(numChunks)]
        curly = [(testcase.parts[i].count(b"{") - testcase.parts[i].count(b"}")) for i in range(numChunks)]
        square = [(testcase.parts[i].count(b"[") - testcase.parts[i].count(b"]")) for i in range(numChunks)]
        normal = [(testcase.parts[i].count(b"(") - testcase.parts[i].count(b")")) for i in range(numChunks)]
        chunkStart = 0  # pylint: disable=invalid-name
        lhsChunkIdx = 0  # pylint: disable=invalid-name

        try:
            while chunkStart < len(testcase.parts):

                description = "chunk #%d%s of %d chunks of size %d" % (
                    lhsChunkIdx, "".join(" " for i in range(len(str(lhsChunkIdx)) + 4)), numChunks, chunkSize)

                assert summary[:lhsChunkIdx].count("S") * chunkSize == chunkStart, (
                    "the chunkStart should correspond to the lhsChunkIdx modulo the removed chunks.")

                chunkLhsStart = chunkStart  # pylint: disable=invalid-name
                chunkLhsEnd = min(len(testcase.parts), chunkLhsStart + chunkSize)  # pylint: disable=invalid-name

                nCurly = curly[lhsChunkIdx]  # pylint: disable=invalid-name
                nSquare = square[lhsChunkIdx]  # pylint: disable=invalid-name
                nNormal = normal[lhsChunkIdx]  # pylint: disable=invalid-name

                # If the chunk is already balanced, try to remove it.
                if not (nCurly or nSquare or nNormal):
                    testcaseSuggestion = testcase.copy()  # pylint: disable=invalid-name
                    testcaseSuggestion.parts = (testcaseSuggestion.parts[:chunkLhsStart] +
                                                testcaseSuggestion.parts[chunkLhsEnd:])
                    if interesting(testcaseSuggestion):
                        testcase = testcaseSuggestion
                        log.info("Yay, reduced it by removing %s :)", description)
                        chunksRemoved += 1  # pylint: disable=invalid-name
                        atomsRemoved += (chunkLhsEnd - chunkLhsStart)  # pylint: disable=invalid-name
                        summary[lhsChunkIdx] = "-"
                    else:
                        log.info("Removing %s made the file 'uninteresting'.", description)
                        chunkStart += chunkSize  # pylint: disable=invalid-name
                    lhsChunkIdx = self.list_nindex(summary, lhsChunkIdx, "S")  # pylint: disable=invalid-name
                    continue

                # Otherwise look for the corresponding chunk.
                rhsChunkIdx = lhsChunkIdx  # pylint: disable=invalid-name
                for item in summary[(lhsChunkIdx + 1):]:
                    rhsChunkIdx += 1  # pylint: disable=invalid-name
                    if item != "S":
                        continue
                    nCurly += curly[rhsChunkIdx]  # pylint: disable=invalid-name
                    nSquare += square[rhsChunkIdx]  # pylint: disable=invalid-name
                    nNormal += normal[rhsChunkIdx]  # pylint: disable=invalid-name
                    if nCurly < 0 or nSquare < 0 or nNormal < 0:
                        break
                    if not (nCurly or nSquare or nNormal):
                        break

                # If we have no match, then just skip this pair of chunks.
                if nCurly or nSquare or nNormal:
                    log.info("Skipping %s because it is 'uninteresting'.", description)
                    chunkStart += chunkSize  # pylint: disable=invalid-name
                    lhsChunkIdx = self.list_nindex(summary, lhsChunkIdx, "S")  # pylint: disable=invalid-name
                    continue

                # Otherwise we do have a match and we check if this is interesting to remove both.
                # pylint: disable=invalid-name
                chunkRhsStart = chunkLhsStart + chunkSize * summary[lhsChunkIdx:rhsChunkIdx].count("S")
                chunkRhsStart = min(len(testcase.parts), chunkRhsStart)  # pylint: disable=invalid-name
                chunkRhsEnd = min(len(testcase.parts), chunkRhsStart + chunkSize)  # pylint: disable=invalid-name

                description = "chunk #%d & #%d of %d chunks of size %d" % (
                    lhsChunkIdx, rhsChunkIdx, numChunks, chunkSize)

                testcaseSuggestion = testcase.copy()
                testcaseSuggestion.parts = (testcaseSuggestion.parts[:chunkLhsStart] +
                                            testcaseSuggestion.parts[chunkLhsEnd:chunkRhsStart] +
                                            testcaseSuggestion.parts[chunkRhsEnd:])
                if interesting(testcaseSuggestion):
                    testcase = testcaseSuggestion
                    log.info("Yay, reduced it by removing %s :)", description)
                    chunksRemoved += 2
                    atomsRemoved += (chunkLhsEnd - chunkLhsStart)
                    atomsRemoved += (chunkRhsEnd - chunkRhsStart)
                    summary[lhsChunkIdx] = "-"
                    summary[rhsChunkIdx] = "-"
                    lhsChunkIdx = self.list_nindex(summary, lhsChunkIdx, "S")
                    continue

                # Removing the braces make the failure disappear.  As we are looking
                # for removing chunk (braces), we need to make the content within
                # the braces as minimal as possible, so let us try to see if we can
                # move the chunks outside the braces.
                log.info("Removing %s made the file 'uninteresting'.", description)

                # Moving chunks is still a bit experimental, and it can introduce reducing loops.
                # If you want to try it, just replace this True by a False.
                if True:  # pylint: disable=using-constant-test
                    chunkStart += chunkSize
                    lhsChunkIdx = self.list_nindex(summary, lhsChunkIdx, "S")
                    continue

                origChunkIdx = lhsChunkIdx
                stayOnSameChunk = False
                chunkMidStart = chunkLhsEnd
                midChunkIdx = self.list_nindex(summary, lhsChunkIdx, "S")
                while chunkMidStart < chunkRhsStart:
                    assert summary[:midChunkIdx].count("S") * chunkSize == chunkMidStart, (
                        "the chunkMidStart should correspond to the midChunkIdx modulo the removed chunks.")
                    description = "chunk #%d%s of %d chunks of size %d" % (
                        midChunkIdx, "".join(" " for i in range(len(str(lhsChunkIdx)) + 4)), numChunks, chunkSize)

                    p = self.list_fiveParts(testcase.parts, chunkSize, chunkLhsStart, chunkMidStart, chunkRhsStart)

                    nCurly = curly[midChunkIdx]
                    nSquare = square[midChunkIdx]
                    nNormal = normal[midChunkIdx]
                    if nCurly or nSquare or nNormal:
                        log.info("Keeping %s because it is 'uninteresting'.", description)
                        chunkMidStart += chunkSize
                        midChunkIdx = self.list_nindex(summary, midChunkIdx, "S")
                        continue

                    # Try moving the chunk after.
                    testcaseSuggestion = testcase.copy()
                    testcaseSuggestion.parts = p[0] + p[1] + p[3] + p[2] + p[4]
                    if interesting(testcaseSuggestion):
                        testcase = testcaseSuggestion
                        log.info("->Moving %s kept the file 'interesting'.", description)
                        chunkRhsStart -= chunkSize
                        chunkRhsEnd -= chunkSize
                        # pylint: disable=bad-whitespace
                        tS = self.list_fiveParts(summary, 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                        tc = self.list_fiveParts(curly  , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)  # noqa
                        ts = self.list_fiveParts(square , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)  # noqa
                        tn = self.list_fiveParts(normal , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)  # noqa
                        summary = tS[0] + tS[1] + tS[3] + tS[2] + tS[4]
                        curly =   tc[0] + tc[1] + tc[3] + tc[2] + tc[4]  # noqa
                        square =  ts[0] + ts[1] + ts[3] + ts[2] + ts[4]  # noqa
                        normal =  tn[0] + tn[1] + tn[3] + tn[2] + tn[4]  # noqa
                        rhsChunkIdx -= 1
                        midChunkIdx = summary[midChunkIdx:].index("S") + midChunkIdx
                        continue

                    # Try moving the chunk before.
                    testcaseSuggestion.parts = p[0] + p[2] + p[1] + p[3] + p[4]
                    if interesting(testcaseSuggestion):
                        testcase = testcaseSuggestion
                        log.info("<-Moving %s kept the file 'interesting'.", description)
                        chunkLhsStart += chunkSize
                        chunkLhsEnd += chunkSize
                        chunkMidStart += chunkSize
                        # pylint: disable=bad-whitespace
                        tS = self.list_fiveParts(summary, 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                        tc = self.list_fiveParts(curly  , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)  # noqa
                        ts = self.list_fiveParts(square , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)  # noqa
                        tn = self.list_fiveParts(normal , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)  # noqa
                        summary = tS[0] + tS[2] + tS[1] + tS[3] + tS[4]
                        curly =   tc[0] + tc[2] + tc[1] + tc[3] + tc[4]  # noqa
                        square =  ts[0] + ts[2] + ts[1] + ts[3] + ts[4]  # noqa
                        normal =  tn[0] + tn[2] + tn[1] + tn[3] + tn[4]  # noqa
                        lhsChunkIdx += 1
                        midChunkIdx = self.list_nindex(summary, midChunkIdx, "S")
                        stayOnSameChunk = True
                        continue

                    log.info("..Moving %s made the file 'uninteresting'.", description)
                    chunkMidStart += chunkSize
                    midChunkIdx = self.list_nindex(summary, midChunkIdx, "S")

                lhsChunkIdx = origChunkIdx
                if not stayOnSameChunk:
                    chunkStart += chunkSize
                    lhsChunkIdx = self.list_nindex(summary, lhsChunkIdx, "S")

        except ValueError:
            # This is a valid loop exit point.
            chunkStart = len(testcase.parts)  # pylint: disable=invalid-name

        atomsSurviving = atomsInitial - atomsRemoved  # pylint: disable=invalid-name
        printableSummary = " ".join(  # pylint: disable=invalid-name
            "".join(summary[(2 * i):min(2 * (i + 1), numChunks + 1)]) for i in range(numChunks // 2 + numChunks % 2))
        log.info("")
        log.info("Done with a round of chunk size %d!", chunkSize)
        log.info("%s survived; %s removed.",
                 quantity(summary.count("S"), "chunk"),
                 quantity(summary.count("-"), "chunk"))
        log.info("%s survived; %s removed.",
                 quantity(atomsSurviving, testcase.atom),
                 quantity(atomsRemoved, testcase.atom))
        log.info("Which chunks survived: %s", printableSummary)
        log.info("")

        testcase.writeTestcase(tempFilename("did-round-%d" % chunkSize))

        return bool(chunksRemoved), testcase


class ReplacePropertiesByGlobals(Minimize):
    """    This strategy attempts to remove members, such that other strategies can
    then move the lines outside the functions.  The goal is to rename
    variables at the same time, such that the program remains valid, while
    removing the dependency on the object on which the member is part of.

      function Foo() {
        this.list = [];
      }
      Foo.prototype.push = function(a) {
        this.list.push(a);
      }
      Foo.prototype.last = function() {
        return this.list.pop();
      }

    Which might transform the previous example to something like:

      function Foo() {
        list = [];
      }
      push = function(a) {
        list.push(a);
      }
      last = function() {
        return list.pop();
      }"""

    name = "replace-properties-by-globals"

    def run(self, testcase, interesting, tempFilename):  # pylint: disable=missing-return-doc,missing-return-type-doc
        # pylint: disable=invalid-name
        chunkSize = min(self.minimizeMax, 2 * largestPowerOfTwoSmallerThan(len(testcase.parts)))
        finalChunkSize = max(self.minimizeMin, 1)

        origNumChars = 0
        for line in testcase.parts:
            origNumChars += len(line)

        numChars = origNumChars
        while 1:
            numRemovedChars, testcase = self.tryMakingGlobals(chunkSize, numChars, testcase, interesting, tempFilename)
            numChars -= numRemovedChars

            last = (chunkSize <= finalChunkSize)

            if numRemovedChars and (self.minimizeRepeat == "always" or (self.minimizeRepeat == "last" and last)):
                # Repeat with the same chunk size
                pass
            elif last:
                # Done
                break
            else:
                # Continue with the next smaller chunk size
                chunkSize >>= 1

        log.info("  Initial size: %s", quantity(origNumChars, "character"))
        log.info("  Final size: %s", quantity(numChars, "character"))

        return 0, (finalChunkSize == 1 and self.minimizeRepeat != "never"), testcase

    def tryMakingGlobals(self, chunkSize, numChars, testcase, interesting, tempFilename):
        # pylint: disable=invalid-name,missing-param-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
        # pylint: disable=too-many-arguments,too-many-branches,too-complex,too-many-locals
        """Make a single run through the testcase, trying to remove chunks of size chunkSize.

        Returns True iff any chunks were removed."""

        numRemovedChars = 0
        numChunks = divideRoundingUp(len(testcase.parts), chunkSize)
        finalChunkSize = max(self.minimizeMin, 1)

        # Map words to the chunk indexes in which they are present.
        words = {}
        for chunk, line in enumerate(testcase.parts):
            for match in re.finditer(br"(?<=[\w\d_])\.(\w+)", line):
                word = match.group(1)
                if word not in words:
                    words[word] = [chunk]
                else:
                    words[word] += [chunk]

        # All patterns have been removed sucessfully.
        if not words:
            return 0, testcase

        log.info("Starting a round with chunks of %s.", quantity(chunkSize, testcase.atom))
        summary = list("S" * numChunks)

        for word, chunks in list(words.items()):
            chunkIndexes = {}
            for chunkStart in chunks:
                chunkIdx = chunkStart // chunkSize
                if chunkIdx not in chunkIndexes:
                    chunkIndexes[chunkIdx] = [chunkStart]
                else:
                    chunkIndexes[chunkIdx] += [chunkStart]

            for chunkIdx, chunkStarts in chunkIndexes.items():
                # Unless this is the final size, let's try to remove couple of
                # prefixes, otherwise wait for the final size to remove each of them
                # individually.
                if len(chunkStarts) == 1 and finalChunkSize != chunkSize:
                    continue

                description = "'%s' in chunk #%d of %d chunks of size %d" % (
                    word.decode("utf-8", "replace"), chunkIdx, numChunks, chunkSize)

                maybeRemoved = 0
                newTC = testcase.copy()
                for chunkStart in chunkStarts:
                    subst = re.sub(br"[\w_.]+\." + word, word, newTC.parts[chunkStart])
                    maybeRemoved += len(newTC.parts[chunkStart]) - len(subst)
                    newTC.parts = newTC.parts[:chunkStart] + [subst] + newTC.parts[(chunkStart + 1):]

                if interesting(newTC):
                    testcase = newTC
                    log.info("Yay, reduced it by removing prefixes of %s :)", description)
                    numRemovedChars += maybeRemoved
                    summary[chunkIdx] = "s"
                    words[word] = [c for c in chunks if c not in chunkIndexes]
                    if not words[word]:
                        del words[word]
                else:
                    log.info("Removing prefixes of %s made the file 'uninteresting'.", description)

        numSurvivingChars = numChars - numRemovedChars
        printableSummary = " ".join(
            "".join(summary[(2 * i):min(2 * (i + 1), numChunks + 1)]) for i in range(numChunks // 2 + numChunks % 2))
        log.info("")
        log.info("Done with a round of chunk size %d!", chunkSize)
        log.info("%s survived; %s shortened.",
                 quantity(summary.count("S"), "chunk"),
                 quantity(summary.count("s"), "chunk"))
        log.info("%s survived; %s removed.",
                 quantity(numSurvivingChars, "character"),
                 quantity(numRemovedChars, "character"))
        log.info("Which chunks survived: %s", printableSummary)
        log.info("")

        testcase.writeTestcase(tempFilename("did-round-%d" % chunkSize))

        return numRemovedChars, testcase


class ReplaceArgumentsByGlobals(Minimize):
    """    This strategy attempts to replace arguments by globals, for each named
    argument of a function we add a setter of the global of the same name before
    the function call.  The goal is to remove functions by making empty arguments
    lists instead.

      function foo(a,b) {
        list = a + b;
      }
      foo(2, 3)

    becomes:

      function foo() {
        list = a + b;
      }
      a = 2;
      b = 3;
      foo()

    The next logical step is inlining the body of the function at the call site."""

    name = "replace-arguments-by-globals"

    def run(self, testcase, interesting, tempFilename):  # pylint: disable=missing-return-doc,missing-return-type-doc
        roundNum = 0  # pylint: disable=invalid-name
        while 1:
            # pylint: disable=invalid-name
            numRemovedArguments, testcase = self.tryArgumentsAsGlobals(roundNum, testcase, interesting, tempFilename)
            roundNum += 1  # pylint: disable=invalid-name

            if numRemovedArguments and (self.minimizeRepeat == "always" or self.minimizeRepeat == "last"):
                # Repeat with the same chunk size
                pass
            else:
                # Done
                break

        return 0, False, testcase

    @staticmethod
    def tryArgumentsAsGlobals(roundNum, testcase, interesting, tempFilename):  # pylint: disable=invalid-name
        # pylint: disable=missing-param-doc,missing-return-doc,missing-return-type-doc,missing-type-doc
        # pylint: disable=too-many-branches,too-complex,too-many-locals,too-many-statements
        """Make a single run through the testcase, trying to remove chunks of size chunkSize.

        Returns True iff any chunks were removed."""

        numMovedArguments = 0  # pylint: disable=invalid-name
        numSurvivedArguments = 0  # pylint: disable=invalid-name

        # Map words to the chunk indexes in which they are present.
        functions = {}
        anonymousQueue = []  # pylint: disable=invalid-name
        anonymousStack = []  # pylint: disable=invalid-name
        for chunk, line in enumerate(testcase.parts):
            # Match function definition with at least one argument.
            for match in re.finditer(br"(?:function\s+(\w+)|(\w+)\s*=\s*function)\s*\((\s*\w+\s*(?:,\s*\w+\s*)*)\)",
                                     line):
                fun = match.group(1)
                if fun is None:
                    fun = match.group(2)

                if match.group(3) == b"":
                    args = []
                else:
                    args = match.group(3).split(b",")

                if fun not in functions:
                    functions[fun] = {"defs": args, "argsPattern": match.group(3), "chunk": chunk, "uses": []}
                else:
                    functions[fun]["defs"] = args
                    functions[fun]["argsPattern"] = match.group(3)
                    functions[fun]["chunk"] = chunk

            # Match anonymous function definition, which are surrounded by parentheses.
            for match in re.finditer(br"\(function\s*\w*\s*\(((?:\s*\w+\s*(?:,\s*\w+\s*)*)?)\)\s*{", line):
                if match.group(1) == b"":
                    args = []
                else:
                    args = match.group(1).split(",")
                # pylint: disable=invalid-name
                anonymousStack += [{"defs": args, "chunk": chunk, "use": None, "useChunk": 0}]

            # Match calls of anonymous function.
            for match in re.finditer(br"}\s*\)\s*\(((?:[^()]|\([^,()]*\))*)\)", line):
                if not anonymousStack:
                    continue
                anon = anonymousStack[-1]
                anonymousStack = anonymousStack[:-1]  # pylint: disable=invalid-name
                if match.group(1) == b"" and not anon["defs"]:
                    continue
                if match.group(1) == b"":
                    args = []
                else:
                    args = match.group(1).split(b",")
                anon["use"] = args
                anon["useChunk"] = chunk
                anonymousQueue += [anon]  # pylint: disable=invalid-name

            # match function calls. (and some definitions)
            for match in re.finditer(br"((\w+)\s*\(((?:[^()]|\([^,()]*\))*)\))", line):
                pattern = match.group(1)
                fun = match.group(2)
                if match.group(3) == b"":
                    args = []
                else:
                    args = match.group(3).split(b",")
                if fun not in functions:
                    functions[fun] = {"uses": []}
                functions[fun]["uses"] += [{"values": args, "chunk": chunk, "pattern": pattern}]

        # All patterns have been removed sucessfully.
        if not functions and not anonymousQueue:
            return 0, testcase

        log.info("Starting removing function arguments.")

        for fun, argsMap in functions.items():  # pylint: disable=invalid-name
            description = "arguments of '%s'" % fun.decode("utf-8", "replace")
            if "defs" not in argsMap or not argsMap["uses"]:
                log.info("Ignoring %s because it is 'uninteresting'.", description)
                continue

            maybeMovedArguments = 0  # pylint: disable=invalid-name
            newTC = testcase.copy()  # pylint: disable=invalid-name

            # Remove the function definition arguments
            argDefs = argsMap["defs"]  # pylint: disable=invalid-name
            defChunk = argsMap["chunk"]  # pylint: disable=invalid-name
            subst = newTC.parts[defChunk].replace(argsMap["argsPattern"], b"", 1)
            newTC.parts = newTC.parts[:defChunk] + [subst] + newTC.parts[(defChunk + 1):]

            # Copy callers arguments to globals.
            for argUse in argsMap["uses"]:  # pylint: disable=invalid-name
                values = argUse["values"]
                chunk = argUse["chunk"]
                if chunk == defChunk and values == argDefs:
                    continue
                while len(values) < len(argDefs):
                    values = values + [b"undefined"]
                setters = b"".join((a + b" = " + v + b";\n") for (a, v) in zip(argDefs, values))
                subst = setters + newTC.parts[chunk]
                newTC.parts = newTC.parts[:chunk] + [subst] + newTC.parts[(chunk + 1):]
            maybeMovedArguments += len(argDefs)  # pylint: disable=invalid-name

            if interesting(newTC):
                testcase = newTC
                log.info("Yay, reduced it by removing %s :)", description)
                numMovedArguments += maybeMovedArguments  # pylint: disable=invalid-name
            else:
                numSurvivedArguments += maybeMovedArguments  # pylint: disable=invalid-name
                log.info("Removing %s made the file 'uninteresting'.", description)

            for argUse in argsMap["uses"]:  # pylint: disable=invalid-name
                chunk = argUse["chunk"]
                values = argUse["values"]
                if chunk == defChunk and values == argDefs:
                    continue

                newTC = testcase.copy()  # pylint: disable=invalid-name
                subst = newTC.parts[chunk].replace(argUse["pattern"], fun + b"()", 1)
                if newTC.parts[chunk] == subst:
                    continue
                newTC.parts = newTC.parts[:chunk] + [subst] + newTC.parts[(chunk + 1):]
                maybeMovedArguments = len(values)  # pylint: disable=invalid-name

                descriptionChunk = "%s at %s #%d" % (description, testcase.atom, chunk)  # pylint: disable=invalid-name
                if interesting(newTC):
                    testcase = newTC
                    log.info("Yay, reduced it by removing %s :)", descriptionChunk)
                    numMovedArguments += maybeMovedArguments  # pylint: disable=invalid-name
                else:
                    numSurvivedArguments += maybeMovedArguments  # pylint: disable=invalid-name
                    log.info("Removing %s made the file 'uninteresting'.", descriptionChunk)

        # Remove immediate anonymous function calls.
        for anon in anonymousQueue:
            noopChanges = 0  # pylint: disable=invalid-name
            maybeMovedArguments = 0  # pylint: disable=invalid-name
            newTC = testcase.copy()  # pylint: disable=invalid-name

            argDefs = anon["defs"]  # pylint: disable=invalid-name
            defChunk = anon["chunk"]  # pylint: disable=invalid-name
            values = anon["use"]
            chunk = anon["useChunk"]
            description = "arguments of anonymous function at #%s %d" % (testcase.atom, defChunk)

            # Remove arguments of the function.
            subst = newTC.parts[defChunk].replace(b",".join(argDefs), b"", 1)
            if newTC.parts[defChunk] == subst:
                noopChanges += 1  # pylint: disable=invalid-name
            newTC.parts = newTC.parts[:defChunk] + [subst] + newTC.parts[(defChunk + 1):]

            # Replace arguments by their value in the scope of the function.
            while len(values) < len(argDefs):
                values = values + [b"undefined"]
            setters = b"".join(b"var %s = %s;\n" % (a, v) for a, v in zip(argDefs, values))
            subst = newTC.parts[defChunk] + b"\n" + setters
            if newTC.parts[defChunk] == subst:
                noopChanges += 1  # pylint: disable=invalid-name
            newTC.parts = newTC.parts[:defChunk] + [subst] + newTC.parts[(defChunk + 1):]

            # Remove arguments of the anonymous function call.
            subst = newTC.parts[chunk].replace(b",".join(anon["use"]), b"", 1)
            if newTC.parts[chunk] == subst:
                noopChanges += 1  # pylint: disable=invalid-name
            newTC.parts = newTC.parts[:chunk] + [subst] + newTC.parts[(chunk + 1):]
            maybeMovedArguments += len(values)  # pylint: disable=invalid-name

            if noopChanges == 3:
                continue

            if interesting(newTC):
                testcase = newTC
                log.info("Yay, reduced it by removing %s :)", description)
                numMovedArguments += maybeMovedArguments  # pylint: disable=invalid-name
            else:
                numSurvivedArguments += maybeMovedArguments  # pylint: disable=invalid-name
                log.info("Removing %s made the file 'uninteresting'.", description)

        log.info("")
        log.info("Done with this round!")
        log.info("%s moved;", quantity(numMovedArguments, "argument"))
        log.info("%s survived.", quantity(numSurvivedArguments, "argument"))

        testcase.writeTestcase(tempFilename("did-round-%d" % roundNum))

        return numMovedArguments, testcase


class Lithium(object):  # pylint: disable=missing-docstring,too-many-instance-attributes

    def __init__(self):

        self.strategy = None

        self.conditionScript = None  # pylint: disable=invalid-name
        self.conditionArgs = None  # pylint: disable=invalid-name

        self.testCount = 0  # pylint: disable=invalid-name
        self.testTotal = 0  # pylint: disable=invalid-name

        self.tempDir = None  # pylint: disable=invalid-name

        self.testcase = None
        self.lastInteresting = None  # pylint: disable=invalid-name

        self.tempFileCount = 1  # pylint: disable=invalid-name

    def main(self, args=None):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
        logging.basicConfig(format="%(message)s", level=logging.INFO)
        self.processArgs(args)

        try:
            return self.run()

        except LithiumError as e:  # pylint: disable=invalid-name
            summaryHeader()
            log.error(e)
            return 1

    def run(self):  # pylint: disable=missing-docstring,missing-return-doc,missing-return-type-doc
        if hasattr(self.conditionScript, "init"):
            self.conditionScript.init(self.conditionArgs)

        try:
            if not self.tempDir:
                self.createTempDir()
                log.info("Intermediate files will be stored in %s%s.", self.tempDir, os.sep)

            result = self.strategy.main(self.testcase, self.interesting, self.testcaseTempFilename)

            log.info("  Tests performed: %d", self.testCount)
            log.info("  Test total: %s", quantity(self.testTotal, self.testcase.atom))

            return result

        finally:
            if hasattr(self.conditionScript, "cleanup"):
                self.conditionScript.cleanup(self.conditionArgs)

            # Make sure we exit with an interesting testcase
            if self.lastInteresting is not None:
                self.lastInteresting.writeTestcase()

    def processArgs(self, argv=None):  # pylint: disable=invalid-name,missing-param-doc,missing-type-doc
        # pylint: disable=too-complex,too-many-locals
        """Build list of strategies and testcase types."""

        strategies = {}
        testcaseTypes = {}  # pylint: disable=invalid-name
        for globalValue in globals().values():  # pylint: disable=invalid-name
            if isinstance(globalValue, type):
                if globalValue is not Strategy and issubclass(globalValue, Strategy):
                    assert globalValue.name not in strategies
                    strategies[globalValue.name] = globalValue
                elif globalValue is not Testcase and issubclass(globalValue, Testcase):
                    assert globalValue.atom not in testcaseTypes
                    testcaseTypes[globalValue.atom] = globalValue

        # Try to parse --conflict before anything else
        class ArgParseTry(argparse.ArgumentParser):  # pylint: disable=missing-docstring
            def exit(subself, **kwds):  # pylint: disable=arguments-differ,no-self-argument
                pass

            def error(subself, message):  # pylint: disable=no-self-argument
                pass

        defaultStrategy = "minimize"  # pylint: disable=invalid-name
        assert defaultStrategy in strategies
        strategyParser = ArgParseTry(add_help=False)  # pylint: disable=invalid-name
        strategyParser.add_argument(
            "--strategy",
            default=defaultStrategy,
            choices=strategies.keys())
        args = strategyParser.parse_known_args(argv)
        self.strategy = strategies.get(args[0].strategy if args else None, strategies[defaultStrategy])()

        parser = argparse.ArgumentParser(
            description="Lithium, an automated testcase reduction tool",
            epilog="See docs/using-for-firefox.md for more information.",
            usage="python -m lithium [options] condition [condition options] file-to-reduce")
        grp_opt = parser.add_argument_group(description="Lithium options")
        grp_opt.add_argument(
            "--testcase",
            help="testcase file. default: last argument is used.")
        grp_opt.add_argument(
            "--tempdir",
            help="specify the directory to use as temporary directory.")
        grp_opt.add_argument(
            "-v", "--verbose",
            action="store_true",
            help="enable verbose debug logging")
        grp_atoms = grp_opt.add_mutually_exclusive_group()
        grp_atoms.add_argument(
            "-c", "--char",
            action="store_true",
            help="Don't treat lines as atomic units; "
                 "treat the file as a sequence of characters rather than a sequence of lines.")
        grp_atoms.add_argument(
            "-j", "--js",
            action="store_true",
            help="Same as --char but only operate within JS strings, keeping escapes intact.")
        grp_atoms.add_argument(
            "-s", "--symbol",
            action="store_true",
            help="Treat the file as a sequence of strings separated by tokens. "
                 "The characters by which the strings are delimited are defined by "
                 "the --cutBefore, and --cutAfter options.")
        grp_opt.add_argument(
            "--cutBefore",
            default=TestcaseSymbol.DEFAULT_CUT_BEFORE,
            help="See --symbol. default: %s" % TestcaseSymbol.DEFAULT_CUT_BEFORE.decode("utf-8"))
        grp_opt.add_argument(
            "--cutAfter",
            default=TestcaseSymbol.DEFAULT_CUT_AFTER,
            help="See --symbol. default: %s" % TestcaseSymbol.DEFAULT_CUT_AFTER.decode("utf-8"))
        grp_opt.add_argument(
            "--strategy",
            default=self.strategy.name,  # this has already been parsed above, it's only here for the help message
            choices=strategies.keys(),
            help="reduction strategy to use. default: %s" % defaultStrategy)
        self.strategy.addArgs(parser)
        grp_ext = parser.add_argument_group(description="Condition, condition options and file-to-reduce")
        grp_ext.add_argument(
            "extra_args",
            action="append",
            nargs=argparse.REMAINDER,
            help="condition [condition options] file-to-reduce")

        args = parser.parse_args(argv)
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        self.strategy.processArgs(parser, args)

        self.tempDir = args.tempdir
        atom = TestcaseChar.atom if args.char else TestcaseLine.atom
        atom = TestcaseJsStr.atom if args.js else atom
        atom = TestcaseSymbol.atom if args.symbol else atom

        extra_args = args.extra_args[0]

        if args.testcase:
            testcaseFilename = args.testcase  # pylint: disable=invalid-name
        elif extra_args:
            # can be overridden by --testcase in processOptions
            testcaseFilename = extra_args[-1]  # pylint: disable=invalid-name
        else:
            parser.error("No testcase specified (use --testcase or last condition arg)")
        self.testcase = testcaseTypes[atom]()
        if args.symbol:
            self.testcase.cutBefore = args.cutBefore
            self.testcase.cutAfter = args.cutAfter
        self.testcase.readTestcase(testcaseFilename)

        self.conditionScript = rel_or_abs_import(extra_args[0])
        self.conditionArgs = extra_args[1:]

    def testcaseTempFilename(self, partialFilename, useNumber=True):  # pylint: disable=invalid-name,missing-docstring
        # pylint: disable=missing-return-doc,missing-return-type-doc
        if useNumber:
            partialFilename = "%d-%s" % (self.tempFileCount, partialFilename)
            self.tempFileCount += 1
        return os.path.join(self.tempDir, partialFilename + self.testcase.extension)

    def createTempDir(self):  # pylint: disable=invalid-name,missing-docstring
        i = 1
        while True:
            self.tempDir = "tmp%d" % i
            # To avoid race conditions, we use try/except instead of exists/create
            # Hopefully we don't get any errors other than "File exists" :)
            try:
                os.mkdir(self.tempDir)
                break
            except OSError:
                i += 1

    # If the file is still interesting after the change, changes "parts" and returns True.
    def interesting(self, testcaseSuggestion, writeIt=True):  # pylint: disable=invalid-name,missing-docstring
        # pylint: disable=missing-return-doc,missing-return-type-doc
        if writeIt:
            testcaseSuggestion.writeTestcase()

        self.testCount += 1
        self.testTotal += len(testcaseSuggestion.parts)

        tempPrefix = os.path.join(self.tempDir, "%d" % self.tempFileCount)  # pylint: disable=invalid-name
        inter = self.conditionScript.interesting(self.conditionArgs, tempPrefix)

        # Save an extra copy of the file inside the temp directory.
        # This is useful if you're reducing an assertion and encounter a crash:
        # it gives you a way to try to reproduce the crash.
        if self.tempDir:
            tempFileTag = "interesting" if inter else "boring"  # pylint: disable=invalid-name
            testcaseSuggestion.writeTestcase(self.testcaseTempFilename(tempFileTag))

        if inter:
            self.testcase = testcaseSuggestion
            self.lastInteresting = self.testcase

        return inter


# Helpers

def summaryHeader():  # pylint: disable=invalid-name,missing-docstring
    log.info("=== LITHIUM SUMMARY ===")


def divideRoundingUp(n, d):  # pylint: disable=invalid-name,missing-docstring,missing-return-doc,missing-return-type-doc
    return (n // d) + (1 if n % d != 0 else 0)


def isPowerOfTwo(n):  # pylint: disable=invalid-name,missing-docstring,missing-return-doc,missing-return-type-doc
    return (1 << max(n.bit_length() - 1, 0)) == n


def largestPowerOfTwoSmallerThan(n):  # pylint: disable=invalid-name,missing-docstring
    # pylint: disable=missing-return-doc,missing-return-type-doc
    result = 1 << max(n.bit_length() - 1, 0)
    if result == n and n > 1:
        result >>= 1
    return result


def quantity(n, unit):  # pylint: disable=invalid-name,missing-param-doc
    # pylint: disable=missing-return-doc,missing-return-type-doc,missing-type-doc
    """Convert a quantity to a string, with correct pluralization."""
    r = "%d %s" % (n, unit)  # pylint: disable=invalid-name
    if n != 1:
        r += "s"  # pylint: disable=invalid-name
    return r


def main():
    exit(Lithium().main())


if __name__ == "__main__":
    main()
