#!/usr/bin/env python
# coding=utf-8
# pylint: disable=invalid-name,missing-docstring,too-many-lines,too-many-statements
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import argparse
import logging
import os
import re
import sys
import time

log = logging.getLogger("lithium")


class LithiumError(Exception):
    pass


class Testcase(object):
    """
    Abstract testcase class.

    Implementers should define readTestcaseLine() and writeTestcase() methods.
    """

    def __init__(self):
        self.before = b""
        self.after = b""
        self.parts = []

        self.filename = None
        self.extension = None

    def copy(self):
        new = type(self)()

        new.before = self.before
        new.after = self.after
        new.parts = self.parts[:]

        new.filename = self.filename
        new.extension = self.extension

        return new

    def readTestcase(self, filename):
        hasDDSection = False

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
                    hasDDSection = True
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

    def readTestcaseWithDDSection(self, f):
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

    def readTestcaseLine(self, line):
        raise NotImplementedError()

    def writeTestcase(self, filename=None):
        raise NotImplementedError()


class TestcaseLine(Testcase):
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


class TestcaseChar(TestcaseLine):
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


class TestcaseSymbol(TestcaseLine):
    atom = "symbol-delimiter"
    DEFAULT_CUT_AFTER = b"?=;{["
    DEFAULT_CUT_BEFORE = b"]}:"

    def __init__(self):
        TestcaseLine.__init__(self)

        self.cutAfter = self.DEFAULT_CUT_AFTER
        self.cutBefore = self.DEFAULT_CUT_BEFORE

    def readTestcaseLine(self, line):
        cutter = (b"[" + self.cutBefore + b"]?" +
                  b"[^" + self.cutBefore + self.cutAfter + b"]*" +
                  b"(?:[" + self.cutAfter + b"]|$|(?=[" + self.cutBefore + b"]))")
        for statement in re.finditer(cutter, line):
            if statement.group(0):
                self.parts.append(statement.group(0))


class Strategy(object):
    """
    Abstract minimization strategy class

    Implementers should define a main() method which takes a testcase and calls the interesting callback repeatedly
    to minimize the testcase.
    """

    def addArgs(self, parser):
        pass

    def processArgs(self, parser, args):
        pass

    def main(self, testcase, interesting, tempFilename):
        raise NotImplementedError()


class CheckOnly(Strategy):
    name = "check-only"

    def main(self, testcase, interesting, tempFilename):
        r = interesting(testcase, writeIt=False)
        log.info("Lithium result: %s", ("interesting." if r else "not interesting."))
        return 0


class Minimize(Strategy):
    name = "minimize"

    def __init__(self):
        self.minimizeRepeat = "last"
        self.minimizeMin = 1
        self.minimizeMax = pow(2, 30)
        self.minimizeChunkStart = 0
        self.minimizeChunkSize = None
        self.minimizeRepeatFirstRound = False
        self.stopAfterTime = None

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

    def main(self, testcase, interesting, tempFilename):
        log.info("The original testcase has %s.", quantity(len(testcase.parts), testcase.atom))
        log.info("Checking that the original testcase is 'interesting'...")
        if not interesting(testcase, writeIt=False):
            log.info("Lithium result: the original testcase is not 'interesting'!")
            return 1

        if not testcase.parts:
            log.info("The file has %s so there's nothing for Lithium to try to remove!", quantity(0, testcase.atom))

        testcase.writeTestcase(tempFilename("original", False))

        origNumParts = len(testcase.parts)
        result, anySingle, testcase = self.run(testcase, interesting, tempFilename)

        testcase.writeTestcase()

        summaryHeader()

        if anySingle:
            log.info("  Removing any single %s from the final file makes it uninteresting!", testcase.atom)

        log.info("  Initial size: %s", quantity(origNumParts, testcase.atom))
        log.info("  Final size: %s", quantity(len(testcase.parts), testcase.atom))

        return result

    # Main reduction algorithm
    #
    # This strategy attempts to remove chunks which might not be interesting
    # code, but which can be removed independently of any other.  This happens
    # frequently with values which are computed, but either after the execution,
    # or never used to influenced the interesting part.
    #
    #   a = compute();
    #   b = compute();   <-- !!!
    #   interesting(a);
    #   c = compute();   <-- !!!
    #
    def run(self, testcase, interesting, tempFilename):
        chunkSize = min(self.minimizeMax, largestPowerOfTwoSmallerThan(len(testcase.parts)))
        finalChunkSize = min(chunkSize, max(self.minimizeMin, 1))
        chunkStart = self.minimizeChunkStart
        anyChunksRemoved = self.minimizeRepeatFirstRound

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
                    chunkSize >>= 1
                    log.info("Halving chunk size to %d", chunkSize)
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
    name = "minimize-around"

    # This strategy attempts to remove pairs of chunks which might be surrounding
    # interesting code, but which cannot be removed independently of the other.
    # This happens frequently with patterns such as:
    #
    #   a = 42;
    #   while (true) {
    #      b = foo(a);      <-- !!!
    #      interesting();
    #      a = bar(b);      <-- !!!
    #   }
    #
    def run(self, testcase, interesting, tempFilename):
        chunkSize = min(self.minimizeMax, largestPowerOfTwoSmallerThan(len(testcase.parts)))
        finalChunkSize = max(self.minimizeMin, 1)

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
    def list_rindex(l, p, e):
        if p < 0 or p > len(l):
            raise ValueError("%s is not in list" % e)
        for index, item in enumerate(reversed(l[:p])):
            if item == e:
                return p - index - 1
        raise ValueError("%s is not in list" % e)

    @staticmethod
    def list_nindex(l, p, e):
        if p + 1 >= len(l):
            raise ValueError("%s is not in list" % e)
        return l[(p + 1):].index(e) + (p + 1)

    def tryRemovingChunks(self, chunkSize, testcase, interesting, tempFilename):  # pylint: disable=too-many-locals
        """Make a single run through the testcase, trying to remove chunks of size chunkSize.

        Returns True iff any chunks were removed."""

        summary = ""

        chunksRemoved = 0
        atomsRemoved = 0

        atomsInitial = len(testcase.parts)
        numChunks = divideRoundingUp(len(testcase.parts), chunkSize)

        # Not enough chunks to remove surrounding blocks.
        if numChunks < 3:
            return False, testcase

        log.info("Starting a round with chunks of %s.", quantity(chunkSize, testcase.atom))

        summary = ["S" for _ in range(numChunks)]
        chunkStart = chunkSize
        beforeChunkIdx = 0
        keepChunkIdx = 1
        afterChunkIdx = 2

        try:
            while chunkStart + chunkSize < len(testcase.parts):
                chunkBefStart = max(0, chunkStart - chunkSize)
                chunkBefEnd = chunkStart
                chunkAftStart = min(len(testcase.parts), chunkStart + chunkSize)
                chunkAftEnd = min(len(testcase.parts), chunkAftStart + chunkSize)
                description = "chunk #%d & #%d of %d chunks of size %d" % (
                    beforeChunkIdx, afterChunkIdx, numChunks, chunkSize)

                testcaseSuggestion = testcase.copy()
                testcaseSuggestion.parts = (testcaseSuggestion.parts[:chunkBefStart] +
                                            testcaseSuggestion.parts[chunkBefEnd:chunkAftStart] +
                                            testcaseSuggestion.parts[chunkAftEnd:])
                if interesting(testcaseSuggestion):
                    testcase = testcaseSuggestion
                    log.info("Yay, reduced it by removing %s :)", description)
                    chunksRemoved += 2
                    atomsRemoved += (chunkBefEnd - chunkBefStart)
                    atomsRemoved += (chunkAftEnd - chunkAftStart)
                    summary[beforeChunkIdx] = "-"
                    summary[afterChunkIdx] = "-"
                    # The start is now sooner since we remove the chunk which was before this one.
                    chunkStart -= chunkSize
                    try:
                        # Try to keep removing surrounding chunks of the same part.
                        beforeChunkIdx = self.list_rindex(summary, keepChunkIdx, "S")
                    except ValueError:
                        # There is no more survinving block on the left-hand-side of
                        # the current chunk, shift everything by one surviving
                        # block. Any ValueError from here means that there is no
                        # longer enough chunk.
                        beforeChunkIdx = keepChunkIdx
                        keepChunkIdx = self.list_nindex(summary, keepChunkIdx, "S")
                        chunkStart += chunkSize
                else:
                    log.info("Removing %s made the file 'uninteresting'.", description)
                    # Shift chunk indexes, and seek the next surviving chunk. ValueError
                    # from here means that there is no longer enough chunks.
                    beforeChunkIdx = keepChunkIdx
                    keepChunkIdx = afterChunkIdx
                    chunkStart += chunkSize

                afterChunkIdx = self.list_nindex(summary, keepChunkIdx, "S")

        except ValueError:
            # This is a valid loop exit point.
            chunkStart = len(testcase.parts)

        atomsSurviving = atomsInitial - atomsRemoved
        printableSummary = " ".join(
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

        return (chunksRemoved > 0), testcase


class MinimizeBalancedPairs(MinimizeSurroundingPairs):
    name = "minimize-balanced"

    # This strategy attempts to remove balanced chunks which might be surrounding
    # interesting code, but which cannot be removed independently of the other.
    # This happens frequently with patterns such as:
    #
    #   ...;
    #   if (cond) {        <-- !!!
    #      ...;
    #      interesting();
    #      ...;
    #   }                  <-- !!!
    #   ...;
    #
    # The value of the condition might not be interesting, but in order to reach the
    # interesting code we still have to compute it, and keep extra code alive.
    #

    @staticmethod
    def list_fiveParts(lst, step, f, s, t):
        return (lst[:f], lst[f:s], lst[s:(s + step)], lst[(s + step):(t + step)], lst[(t + step):])

    def tryRemovingChunks(self,  # pylint: disable=too-many-branches,too-many-locals
                          chunkSize, testcase, interesting, tempFilename):
        """Make a single run through the testcase, trying to remove chunks of size chunkSize.

        Returns True iff any chunks were removed."""

        summary = ""

        chunksRemoved = 0
        atomsRemoved = 0

        atomsInitial = len(testcase.parts)
        numChunks = divideRoundingUp(len(testcase.parts), chunkSize)

        # Not enough chunks to remove surrounding blocks.
        if numChunks < 2:
            return False, testcase

        log.info("Starting a round with chunks of %s.", quantity(chunkSize, testcase.atom))

        summary = ["S" for i in range(numChunks)]
        curly = [(testcase.parts[i].count(b"{") - testcase.parts[i].count(b"}")) for i in range(numChunks)]
        square = [(testcase.parts[i].count(b"[") - testcase.parts[i].count(b"]")) for i in range(numChunks)]
        normal = [(testcase.parts[i].count(b"(") - testcase.parts[i].count(b")")) for i in range(numChunks)]
        chunkStart = 0
        lhsChunkIdx = 0

        try:
            while chunkStart < len(testcase.parts):

                description = "chunk #%d%s of %d chunks of size %d" % (
                    lhsChunkIdx, "".join(" " for i in range(len(str(lhsChunkIdx)) + 4)), numChunks, chunkSize)

                assert summary[:lhsChunkIdx].count("S") * chunkSize == chunkStart, (
                    "the chunkStart should correspond to the lhsChunkIdx modulo the removed chunks.")

                chunkLhsStart = chunkStart
                chunkLhsEnd = min(len(testcase.parts), chunkLhsStart + chunkSize)

                nCurly = curly[lhsChunkIdx]
                nSquare = square[lhsChunkIdx]
                nNormal = normal[lhsChunkIdx]

                # If the chunk is already balanced, try to remove it.
                if nCurly == 0 and nSquare == 0 and nNormal == 0:
                    testcaseSuggestion = testcase.copy()
                    testcaseSuggestion.parts = (testcaseSuggestion.parts[:chunkLhsStart] +
                                                testcaseSuggestion.parts[chunkLhsEnd:])
                    if interesting(testcaseSuggestion):
                        testcase = testcaseSuggestion
                        log.info("Yay, reduced it by removing %s :)", description)
                        chunksRemoved += 1
                        atomsRemoved += (chunkLhsEnd - chunkLhsStart)
                        summary[lhsChunkIdx] = "-"
                    else:
                        log.info("Removing %s made the file 'uninteresting'.", description)
                        chunkStart += chunkSize
                    lhsChunkIdx = self.list_nindex(summary, lhsChunkIdx, "S")
                    continue

                # Otherwise look for the corresponding chunk.
                rhsChunkIdx = lhsChunkIdx
                for item in summary[(lhsChunkIdx + 1):]:
                    rhsChunkIdx += 1
                    if item != "S":
                        continue
                    nCurly += curly[rhsChunkIdx]
                    nSquare += square[rhsChunkIdx]
                    nNormal += normal[rhsChunkIdx]
                    if nCurly < 0 or nSquare < 0 or nNormal < 0:
                        break
                    if nCurly == 0 and nSquare == 0 and nNormal == 0:
                        break

                # If we have no match, then just skip this pair of chunks.
                if nCurly != 0 or nSquare != 0 or nNormal != 0:
                    log.info("Skipping %s because it is 'uninteresting'.", description)
                    chunkStart += chunkSize
                    lhsChunkIdx = self.list_nindex(summary, lhsChunkIdx, "S")
                    continue

                # Otherwise we do have a match and we check if this is interesting to remove both.
                chunkRhsStart = chunkLhsStart + chunkSize * summary[lhsChunkIdx:rhsChunkIdx].count("S")
                chunkRhsStart = min(len(testcase.parts), chunkRhsStart)
                chunkRhsEnd = min(len(testcase.parts), chunkRhsStart + chunkSize)

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
                    if nCurly != 0 or nSquare != 0 or nNormal != 0:
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
            chunkStart = len(testcase.parts)

        atomsSurviving = atomsInitial - atomsRemoved
        printableSummary = " ".join(
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

        return (chunksRemoved > 0), testcase


class ReplacePropertiesByGlobals(Minimize):
    name = "replace-properties-by-globals"

    # This strategy attempts to remove members, such that other strategies can
    # then move the lines outside the functions.  The goal is to rename
    # variables at the same time, such that the program remains valid, while
    # removing the dependency on the object on which the member is part of.
    #
    #   function Foo() {
    #     this.list = [];
    #   }
    #   Foo.prototype.push = function(a) {
    #     this.list.push(a);
    #   }
    #   Foo.prototype.last = function() {
    #     return this.list.pop();
    #   }
    #
    # Which might transform the previous example to something like:
    #
    #   function Foo() {
    #     list = [];
    #   }
    #   push = function(a) {
    #     list.push(a);
    #   }
    #   last = function() {
    #     return list.pop();
    #   }
    #
    def run(self, testcase, interesting, tempFilename):
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

    def tryMakingGlobals(self,  # pylint: disable=too-many-arguments,too-many-branches,too-many-locals
                         chunkSize, numChars, testcase, interesting, tempFilename):
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
    name = "replace-arguments-by-globals"

    # This strategy attempts to replace arguments by globals, for each named
    # argument of a function we add a setter of the global of the same name before
    # the function call.  The goal is to remove functions by making empty arguments
    # lists instead.
    #
    #   function foo(a,b) {
    #     list = a + b;
    #   }
    #   foo(2, 3)
    #
    # becomes:
    #
    #   function foo() {
    #     list = a + b;
    #   }
    #   a = 2;
    #   b = 3;
    #   foo()
    #
    # The next logical step is inlining the body of the function at the call site.
    #
    def run(self, testcase, interesting, tempFilename):
        roundNum = 0
        while 1:
            numRemovedArguments, testcase = self.tryArgumentsAsGlobals(roundNum, testcase, interesting, tempFilename)
            roundNum += 1

            if numRemovedArguments and (self.minimizeRepeat == "always" or self.minimizeRepeat == "last"):
                # Repeat with the same chunk size
                pass
            else:
                # Done
                break

        return 0, False, testcase

    @staticmethod
    def tryArgumentsAsGlobals(roundNum,  # pylint: disable=too-many-branches,too-many-locals
                              testcase, interesting, tempFilename):
        """Make a single run through the testcase, trying to remove chunks of size chunkSize.

        Returns True iff any chunks were removed."""

        numMovedArguments = 0
        numSurvivedArguments = 0

        # Map words to the chunk indexes in which they are present.
        functions = {}
        anonymousQueue = []
        anonymousStack = []
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
                if match.group(1) == "":
                    args = []
                else:
                    args = match.group(1).split(",")
                anonymousStack += [{"defs": args, "chunk": chunk, "use": None, "useChunk": 0}]

            # Match calls of anonymous function.
            for match in re.finditer(br"}\s*\)\s*\(((?:[^()]|\([^,()]*\))*)\)", line):
                if not anonymousStack:
                    continue
                anon = anonymousStack[-1]
                anonymousStack = anonymousStack[:-1]
                if match.group(1) == b"" and not anon["defs"]:
                    continue
                if match.group(1) == b"":
                    args = []
                else:
                    args = match.group(1).split(b",")
                anon["use"] = args
                anon["useChunk"] = chunk
                anonymousQueue += [anon]

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

        for fun, argsMap in functions.items():
            description = "arguments of '%s'" % fun.decode("utf-8", "replace")
            if "defs" not in argsMap or not argsMap["uses"]:
                log.info("Ignoring %s because it is 'uninteresting'.", description)
                continue

            maybeMovedArguments = 0
            newTC = testcase.copy()

            # Remove the function definition arguments
            argDefs = argsMap["defs"]
            defChunk = argsMap["chunk"]
            subst = newTC.parts[defChunk].replace(argsMap["argsPattern"], b"", 1)
            newTC.parts = newTC.parts[:defChunk] + [subst] + newTC.parts[(defChunk + 1):]

            # Copy callers arguments to globals.
            for argUse in argsMap["uses"]:
                values = argUse["values"]
                chunk = argUse["chunk"]
                if chunk == defChunk and values == argDefs:
                    continue
                while len(values) < len(argDefs):
                    values = values + [b"undefined"]
                setters = b"".join((a + b" = " + v + b";\n") for (a, v) in zip(argDefs, values))
                subst = setters + newTC.parts[chunk]
                newTC.parts = newTC.parts[:chunk] + [subst] + newTC.parts[(chunk + 1):]
            maybeMovedArguments += len(argDefs)

            if interesting(newTC):
                testcase = newTC
                log.info("Yay, reduced it by removing %s :)", description)
                numMovedArguments += maybeMovedArguments
            else:
                numSurvivedArguments += maybeMovedArguments
                log.info("Removing %s made the file 'uninteresting'.", description)

            for argUse in argsMap["uses"]:
                chunk = argUse["chunk"]
                values = argUse["values"]
                if chunk == defChunk and values == argDefs:
                    continue

                newTC = testcase.copy()
                subst = newTC.parts[chunk].replace(argUse["pattern"], fun + b"()", 1)
                if newTC.parts[chunk] == subst:
                    continue
                newTC.parts = newTC.parts[:chunk] + [subst] + newTC.parts[(chunk + 1):]
                maybeMovedArguments = len(values)

                descriptionChunk = "%s at %s #%d" % (description, testcase.atom, chunk)
                if interesting(newTC):
                    testcase = newTC
                    log.info("Yay, reduced it by removing %s :)", descriptionChunk)
                    numMovedArguments += maybeMovedArguments
                else:
                    numSurvivedArguments += maybeMovedArguments
                    log.info("Removing %s made the file 'uninteresting'.", descriptionChunk)

        # Remove immediate anonymous function calls.
        for anon in anonymousQueue:
            noopChanges = 0
            maybeMovedArguments = 0
            newTC = testcase.copy()

            argDefs = anon["defs"]
            defChunk = anon["chunk"]
            values = anon["use"]
            chunk = anon["useChunk"]
            description = "arguments of anonymous function at #%s %d" % (testcase.atom, defChunk)

            # Remove arguments of the function.
            subst = newTC.parts[defChunk].replace(b",".join(argDefs), b"", 1)
            if newTC.parts[defChunk] == subst:
                noopChanges += 1
            newTC.parts = newTC.parts[:defChunk] + [subst] + newTC.parts[(defChunk + 1):]

            # Replace arguments by their value in the scope of the function.
            while len(values) < len(argDefs):
                values = values + [b"undefined"]
            setters = b"".join(b"var %s = %s;\n" % (a, v) for a, v in zip(argDefs, values))
            subst = newTC.parts[defChunk] + b"\n" + setters
            if newTC.parts[defChunk] == subst:
                noopChanges += 1
            newTC.parts = newTC.parts[:defChunk] + [subst] + newTC.parts[(defChunk + 1):]

            # Remove arguments of the anonymous function call.
            subst = newTC.parts[chunk].replace(b",".join(anon["use"]), b"", 1)
            if newTC.parts[chunk] == subst:
                noopChanges += 1
            newTC.parts = newTC.parts[:chunk] + [subst] + newTC.parts[(chunk + 1):]
            maybeMovedArguments += len(values)

            if noopChanges == 3:
                continue

            if interesting(newTC):
                testcase = newTC
                log.info("Yay, reduced it by removing %s :)", description)
                numMovedArguments += maybeMovedArguments
            else:
                numSurvivedArguments += maybeMovedArguments
                log.info("Removing %s made the file 'uninteresting'.", description)

        log.info("")
        log.info("Done with this round!")
        log.info("%s moved;", quantity(numMovedArguments, "argument"))
        log.info("%s survived.", quantity(numSurvivedArguments, "argument"))

        testcase.writeTestcase(tempFilename("did-round-%d" % roundNum))

        return numMovedArguments, testcase


class Lithium(object):  # pylint: disable=too-many-instance-attributes

    def __init__(self):

        self.strategy = None

        self.conditionScript = None
        self.conditionArgs = None

        self.testCount = 0
        self.testTotal = 0

        self.tempDir = None

        self.testcase = None
        self.lastInteresting = None

        self.tempFileCount = 1

    def main(self, args=None):
        logging.basicConfig(format="%(message)s", level=logging.INFO)
        self.processArgs(args)

        try:
            return self.run()

        except LithiumError as e:
            summaryHeader()
            log.error(e)
            return 1

    def run(self):
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

    def processArgs(self, argv=None):  # pylint: disable=too-many-locals
        # Build list of strategies and testcase types
        strategies = {}
        testcaseTypes = {}
        for globalValue in globals().values():
            if isinstance(globalValue, type):
                if globalValue is not Strategy and issubclass(globalValue, Strategy):
                    assert globalValue.name not in strategies
                    strategies[globalValue.name] = globalValue
                elif globalValue is not Testcase and issubclass(globalValue, Testcase):
                    assert globalValue.atom not in testcaseTypes
                    testcaseTypes[globalValue.atom] = globalValue

        # Try to parse --conflict before anything else
        class ArgParseTry(argparse.ArgumentParser):
            def exit(subself, **kwds):  # pylint: disable=arguments-differ,no-self-argument
                pass

            def error(subself, message):  # pylint: disable=no-self-argument
                pass

        defaultStrategy = "minimize"
        assert defaultStrategy in strategies
        parser = ArgParseTry(add_help=False)
        parser.add_argument(
            "--strategy",
            default=defaultStrategy,
            choices=strategies.keys())
        args = parser.parse_known_args(argv)
        self.strategy = strategies.get(args[0].strategy if args else None, strategies[defaultStrategy])()

        parser = argparse.ArgumentParser(
            description="Lithium, an automated testcase reduction tool by Jesse Ruderman.",
            epilog="See doc/using.html for more information.",
            usage="./lithium.py [options] condition [condition options] file-to-reduce\n\n"
                  "example: "
                  "./lithium.py crashes 120 ~/tracemonkey/js/src/debug/js -j a.js\n"
                  "    Lithium will reduce a.js subject to the condition that the following\n"
                  "    crashes in 120 seconds:\n"
                  "    ~/tracemonkey/js/src/debug/js -j a.js")
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
        atom = TestcaseSymbol.atom if args.symbol else atom

        extra_args = args.extra_args[0]

        if args.testcase:
            testcaseFilename = args.testcase
        elif extra_args:
            testcaseFilename = extra_args[-1]  # can be overridden by --testcase in processOptions
        else:
            parser.error("No testcase specified (use --testcase or last condition arg)")
        self.testcase = testcaseTypes[atom]()
        if args.symbol:
            self.testcase.cutBefore = args.cutBefore
            self.testcase.cutAfter = args.cutAfter
        self.testcase.readTestcase(testcaseFilename)

        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, "interestingness"))
        import ximport  # pylint: disable=import-error

        self.conditionScript = ximport.importRelativeOrAbsolute(extra_args[0])
        self.conditionArgs = extra_args[1:]

    def testcaseTempFilename(self, partialFilename, useNumber=True):
        if useNumber:
            partialFilename = "%d-%s" % (self.tempFileCount, partialFilename)
            self.tempFileCount += 1
        return os.path.join(self.tempDir, partialFilename + self.testcase.extension)

    def createTempDir(self):
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
    def interesting(self, testcaseSuggestion, writeIt=True):
        if writeIt:
            testcaseSuggestion.writeTestcase()

        self.testCount += 1
        self.testTotal += len(testcaseSuggestion.parts)

        tempPrefix = os.path.join(self.tempDir, "%d" % self.tempFileCount)
        inter = self.conditionScript.interesting(self.conditionArgs, tempPrefix)

        # Save an extra copy of the file inside the temp directory.
        # This is useful if you're reducing an assertion and encounter a crash:
        # it gives you a way to try to reproduce the crash.
        if self.tempDir:
            tempFileTag = "interesting" if inter else "boring"
            testcaseSuggestion.writeTestcase(self.testcaseTempFilename(tempFileTag))

        if inter:
            self.testcase = testcaseSuggestion
            self.lastInteresting = self.testcase

        return inter


# Helpers

def summaryHeader():
    log.info("=== LITHIUM SUMMARY ===")


def divideRoundingUp(n, d):
    return (n // d) + (1 if n % d != 0 else 0)


def isPowerOfTwo(n):
    return (1 << max(n.bit_length() - 1, 0)) == n


def largestPowerOfTwoSmallerThan(n):
    result = 1 << max(n.bit_length() - 1, 0)
    if result == n and n > 1:
        result >>= 1
    return result


def quantity(n, unit):
    "Convert a quantity to a string, with correct pluralization."
    r = "%d %s" % (n, unit)
    if n != 1:
        r += "s"
    return r


def main():
    exit(Lithium().main())


if __name__ == "__main__":
    main()
