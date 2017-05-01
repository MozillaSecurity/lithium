#!/usr/bin/env python

import argparse
import os
import time
import sys
import re
import string

path0 = os.path.dirname(os.path.realpath(__file__))
path1 = os.path.abspath(os.path.join(path0, os.pardir, 'interestingness'))
sys.path.append(path1)
import ximport

# Globals
strategy = "minimize"
minimizeRepeat = "last"
minimizeMin = 1
minimizeMax = pow(2, 30)
minimizeChunkStart = 0
minimizeRepeatFirstRound = False

atom = "line"
cutAfter = "?=;{["
cutBefore = "]}:"

conditionScript = None
conditionArgs = None
testcaseFilename = None
testcaseExtension = ""

testCount = 0
testTotal = 0

tempDir = None
tempFileCount = 1

before = ""
after = ""
parts = []
interestingParts = None
stopAfterTime = None


def main():
    global conditionScript, conditionArgs, testcaseFilename, testcaseExtension, strategy, parts, interestingParts

    readTestcase()

    if hasattr(conditionScript, "init"):
        conditionScript.init(conditionArgs)

    try:

        if not tempDir:
            createTempDir()
            print "Intermediate files will be stored in " + tempDir + os.sep + "."

        if strategy == "check-only":
            r = interesting(parts, writeIt=False)
            print 'Lithium result: ' + ('interesting.' if r else 'not interesting.')
            return

        strategyFunction = {
            'minimize': minimize,
            'minimize-around': minimizeSurroundingPairs,
            'minimize-balanced': minimizeBalancedPairs,
            'replace-properties-by-globals': replacePropertiesByGlobals,
            'replace-arguments-by-globals': replaceArgumentsByGlobals,
        }.get(strategy, None)

        if not strategyFunction:
            usageError("Unknown strategy!")

        print "The original testcase has " + quantity(len(parts), atom) + "."
        print "Checking that the original testcase is 'interesting'..."
        if not interesting(parts, writeIt=False):
            print "Lithium result: the original testcase is not 'interesting'!"
            return

        if len(parts) == 0:
            print "The file has " + quantity(0, atom) + " so there's nothing for Lithium to try to remove!"

        writeTestcaseTemp("original", False)
        strategyFunction()

    finally:
        if hasattr(conditionScript, "cleanup"):
            conditionScript.cleanup(conditionArgs)
        # Make sure we exit with an interesting testcase
        if interestingParts is not None:
            parts = interestingParts
            writeTestcase(testcaseFilename)



def processOptions():
    global atom, conditionArgs, conditionScript, strategy, testcaseExtension, testcaseFilename, tempDir
    global minimizeRepeat, minimizeMin, minimizeMax, minimizeChunkStart, minimizeRepeatFirstRound, stopAfterTime

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
        "-c", "--char",
        action="store_true",
        help="Don't treat lines as atomic units; treat the file as a sequence of characters rather than a sequence of lines.")
    grp_opt.add_argument(
        "-s", "--symbol",
        action="store_true",
        help="Treat the file as a sequence of strings separated by tokens. " + \
             "The characters by which the strings are delimited are defined by the --cutBefore, and --cutAfter options.")
    grp_opt.add_argument(
        "--strategy",
        default="minimize",
        choices=["check-only", "minimize", "minimize-around", "minimize-balanced",
                 "replace-properties-by-globals", "replace-arguments-by-globals"],
        help="reduction strategy to use. default: minimize")
    grp_add = parser.add_argument_group(description="Additional options for the default strategy")
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
        help="For the first round only, start n chars/lines into the file. Best for max to divide n. [Mostly intended for internal use]")
    grp_add.add_argument(
        "--repeatfirstround", default=False, action="store_true",
        help="Treat the first round as if it removed chunks; possibly repeat it.  [Mostly intended for internal use]")
    grp_add.add_argument(
        "--maxruntime", type=int,
        default=None,
        help="If reduction takes more than n seconds, stop (and print instructions for continuing).")
    grp_ext = parser.add_argument_group(description="Condition, condition options and file-to-reduce")
    grp_ext.add_argument(
        "extra_args",
        action="append",
        nargs=argparse.REMAINDER,
        help="condition [condition options] file-to-reduce")

    args = parser.parse_args()

    tempDir = args.tempdir
    atom = "char" if args.char else "line"
    strategy = args.strategy
    if args.chunksize:
        minimizeMin = args.chunksize
        minimizeMax = args.chunksize
        minimizeRepeat = "never"
    else:
        minimizeMin = args.min
        minimizeMax = args.max
        minimizeRepeat = args.repeat
    minimizeChunkStart = args.chunkstart
    minimizeRepeatFirstRound = args.repeatfirstround
    if args.maxruntime:
        stopAfterTime = time.time() + args.maxruntime
    extra_args = args.extra_args[0]

    if args.testcase:
        testcaseFilename = args.testcase
    elif len(extra_args) > 0:
        testcaseFilename = extra_args[-1]  # can be overridden by --testcase in processOptions
    else:
        print "No testcase specified (use --testcase or last condition arg)"
        return False

    testcaseExtension = os.path.splitext(testcaseFilename)[1]

    if not isPowerOfTwo(minimizeMin) or not isPowerOfTwo(minimizeMax):
        print "Min/Max must be powers of two."
        return False

    conditionScript = ximport.importRelativeOrAbsolute(extra_args[0])
    conditionArgs = extra_args[1:]

    return True


def usageError(s):
    print "=== LITHIUM SUMMARY ==="
    print s
    raise Exception(s)


# Functions for manipulating the testcase (aka the 'interesting' file)
def readTestcase():
    hasDDSection = False

    with open(testcaseFilename, "r") as f:
        # Determine whether the f has a DDBEGIN..DDEND section.
        for line in f:
            if line.find("DDEND") != -1:
                usageError("The testcase (" + testcaseFilename + ") has a line containing 'DDEND' without a line containing 'DDBEGIN' before it.")
            if line.find("DDBEGIN") != -1:
                hasDDSection = True
                break

        f.seek(0)

        if hasDDSection:
            # Reduce only the part of the file between 'DDBEGIN' and 'DDEND',
            # leaving the rest unchanged.
            # print "Testcase has a DD section"
            readTestcaseWithDDSection(f)
        else:
            # Reduce the entire file.
            # print "Testcase does not have a DD section"
            for line in f:
                readTestcaseLine(line)

    global parts, interestingParts
    interestingParts = parts


def readTestcaseWithDDSection(f):
    global before, after
    global parts

    for line in f:
        before += line
        if line.find("DDBEGIN") != -1:
            break

    for line in f:
        if line.find("DDEND") != -1:
            after += line
            break
        readTestcaseLine(line)
    else:
        usageError("The testcase (" + testcaseFilename + ") has a line containing 'DDBEGIN' but no line containing 'DDEND'.")

    for line in f:
        after += line

    if atom == "char" and len(parts) > 0:
        # Move the line break at the end of the last line out of the reducible
        # part so the "DDEND" line doesn't get combined with another line.
        parts.pop()
        after = "\n" + after


def readTestcaseLine(line):
    global atom
    global parts

    if atom == "line":
        parts.append(line)
    elif atom == "char":
        for char in line:
            parts.append(char)
    elif atom == "symbol-delimiter":
        cutter = '[' + cutBefore + ']?[^' + cutBefore + cutAfter + ']*(?:[' + cutAfter + ']|$|(?=[' + cutBefore + ']))'
        for statement in re.finditer(cutter, line):
            parts.append(statement.group(0))


def writeTestcase(filename):
    with open(filename, "w") as f:
        f.write(before)
        f.writelines(parts)
        f.write(after)


def writeTestcaseTemp(partialFilename, useNumber):
    global tempFileCount
    if useNumber:
        partialFilename = str(tempFileCount) + "-" + partialFilename
        tempFileCount += 1
    writeTestcase(tempDir + os.sep + partialFilename + testcaseExtension)


def createTempDir():
    global tempDir
    i = 1
    while True:
        tempDir = "tmp" + str(i)
        # To avoid race conditions, we use try/except instead of exists/create
        # Hopefully we don't get any errors other than "File exists" :)
        try:
            os.mkdir(tempDir)
            break
        except OSError:
            i += 1


# If the file is still interesting after the change, changes the global "parts" and returns True.
def interesting(partsSuggestion, writeIt=True):
    global tempFileCount, testcaseFilename, conditionArgs
    global testCount, testTotal
    global parts, interestingParts
    oldParts = parts  # would rather be less side-effecty about this, and be passing partsSuggestion around
    parts = partsSuggestion

    if writeIt:
        writeTestcase(testcaseFilename)

    testCount += 1
    testTotal += len(parts)

    tempPrefix = tempDir + os.sep + str(tempFileCount)
    inter = conditionScript.interesting(conditionArgs, tempPrefix)

    # Save an extra copy of the file inside the temp directory.
    # This is useful if you're reducing an assertion and encounter a crash:
    # it gives you a way to try to reproduce the crash.
    if tempDir:
        tempFileTag = "interesting" if inter else "boring"
        writeTestcaseTemp(tempFileTag, True)

    if inter:
        interestingParts = parts
    else:
        parts = oldParts
    return inter


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
def minimize():
    global parts, testCount, testTotal
    global minimizeMax, minimizeMin, minimizeChunkStart, minimizeRepeatFirstRound
    origNumParts = len(parts)
    chunkSize = min(minimizeMax, largestPowerOfTwoSmallerThan(origNumParts))
    finalChunkSize = min(chunkSize, max(minimizeMin, 1))
    chunkStart = minimizeChunkStart
    anyChunksRemoved = minimizeRepeatFirstRound

    while True:
        if stopAfterTime and time.time() > stopAfterTime:
            # Not all switches will be copied!  Be sure to add --tempdir, --maxruntime if desired.
            # Not using shellify() here because of the strange requirements of bot.py's lithium-command.txt.
            print "Lithium result: please perform another pass using the same arguments"
            break

        if chunkStart >= len(parts):
            writeTestcaseTemp("did-round-" + str(chunkSize), True)
            last = (chunkSize <= finalChunkSize)
            empty = (len(parts) == 0)
            print ""
            if not empty and anyChunksRemoved and (minimizeRepeat == "always" or (minimizeRepeat == "last" and last)):
                chunkStart = 0
                print "Starting another round of chunk size " + str(chunkSize)
            elif empty or last:
                print "Lithium result: succeeded, reduced to: " + quantity(len(parts), atom)
                break
            else:
                chunkStart = 0
                chunkSize /= 2
                print "Halving chunk size to " + str(chunkSize)
            anyChunksRemoved = False

        chunkEnd = min(len(parts), chunkStart + chunkSize)
        description = "Removing a chunk of size " + str(chunkSize) + " starting at " + str(chunkStart) + " of " + str(len(parts))
        if interesting(parts[:chunkStart] + parts[chunkEnd:]):
            print description + " was a successful reduction :)"
            anyChunksRemoved = True
            # leave chunkStart the same
        else:
            print description + " made the file 'uninteresting'."
            chunkStart += chunkSize

    writeTestcase(testcaseFilename)

    print "=== LITHIUM SUMMARY ==="
    if chunkSize == 1 and not anyChunksRemoved and minimizeRepeat != "never":
        print "  Removing any single " + atom + " from the final file makes it uninteresting!"

    print "  Initial size: " + quantity(origNumParts, atom)
    print "  Final size: " + quantity(len(parts), atom)
    print "  Tests performed: " + str(testCount)
    print "  Test total: " + quantity(testTotal, atom)


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
def minimizeSurroundingPairs():
    origNumParts = len(parts)
    chunkSize = min(minimizeMax, largestPowerOfTwoSmallerThan(origNumParts))
    finalChunkSize = max(minimizeMin, 1)

    while 1:
        anyChunksRemoved = tryRemovingSurroundingChunks(chunkSize)

        last = (chunkSize <= finalChunkSize)

        if anyChunksRemoved and (minimizeRepeat == "always" or (minimizeRepeat == "last" and last)):
            # Repeat with the same chunk size
            pass
        elif last:
            # Done
            break
        else:
            # Continue with the next smaller chunk size
            chunkSize /= 2

    writeTestcase(testcaseFilename)

    print "=== LITHIUM SUMMARY ==="

    if finalChunkSize == 1 and minimizeRepeat != "never":
        print "  Removing any single " + atom + " from the final file makes it uninteresting!"

    print "  Initial size: " + quantity(origNumParts, atom)
    print "  Final size: " + quantity(len(parts), atom)
    print "  Tests performed: " + str(testCount)
    print "  Test total: " + quantity(testTotal, atom)


def list_rindex(l, p, e):
    if p < 0 or p > len(l):
        raise ValueError("%s is not in list" % str(e))
    for index, item in enumerate(reversed(l[:p])):
        if item == e:
            return p - index - 1
    raise ValueError("%s is not in list" % str(e))


def list_nindex(l, p, e):
    if p + 1 >= len(l):
        raise ValueError("%s is not in list" % str(e))
    return l[(p + 1):].index(e) + (p + 1)


def tryRemovingSurroundingChunks(chunkSize):
    """Make a single run through the testcase, trying to remove chunks of size chunkSize.

    Returns True iff any chunks were removed."""

    global parts

    chunksSoFar = 0
    summary = ""

    chunksRemoved = 0
    chunksSurviving = 0
    atomsRemoved = 0

    atomsInitial = len(parts)
    numChunks = divideRoundingUp(len(parts), chunkSize)

    # Not enough chunks to remove surrounding blocks.
    if numChunks < 3:
        return False

    print "Starting a round with chunks of " + quantity(chunkSize, atom) + "."

    summary = ['S' for i in range(numChunks)]
    chunkStart = chunkSize
    beforeChunkIdx = 0
    keepChunkIdx = 1
    afterChunkIdx = 2

    try:
        while chunkStart + chunkSize < len(parts):
            chunkBefStart = max(0, chunkStart - chunkSize)
            chunkBefEnd = chunkStart
            chunkAftStart = min(len(parts), chunkStart + chunkSize)
            chunkAftEnd = min(len(parts), chunkAftStart + chunkSize)
            description = "chunk #" + str(beforeChunkIdx) + " & #" + str(afterChunkIdx) + " of " + str(numChunks) + " chunks of size " + str(chunkSize)

            if interesting(parts[:chunkBefStart] + parts[chunkBefEnd:chunkAftStart] + parts[chunkAftEnd:]):
                print "Yay, reduced it by removing " + description + " :)"
                chunksRemoved += 2
                atomsRemoved += (chunkBefEnd - chunkBefStart)
                atomsRemoved += (chunkAftEnd - chunkAftStart)
                summary[beforeChunkIdx] = '-'
                summary[afterChunkIdx] = '-'
                # The start is now sooner since we remove the chunk which was before this one.
                chunkStart -= chunkSize
                try:
                    # Try to keep removing surrounding chunks of the same part.
                    beforeChunkIdx = list_rindex(summary, keepChunkIdx, 'S')
                except ValueError:
                    # There is no more survinving block on the left-hand-side of
                    # the current chunk, shift everything by one surviving
                    # block. Any ValueError from here means that there is no
                    # longer enough chunk.
                    beforeChunkIdx = keepChunkIdx
                    keepChunkIdx = list_nindex(summary, keepChunkIdx, 'S')
                    chunkStart += chunkSize
            else:
                print "Removing " + description + " made the file 'uninteresting'."
                # Shift chunk indexes, and seek the next surviving chunk. ValueError
                # from here means that there is no longer enough chunks.
                beforeChunkIdx = keepChunkIdx
                keepChunkIdx = afterChunkIdx
                chunkStart += chunkSize

            afterChunkIdx = list_nindex(summary, keepChunkIdx, 'S')

    except ValueError:
        # This is a valid loop exit point.
        chunkStart = len(parts)

    atomsSurviving = atomsInitial - atomsRemoved
    printableSummary = " ".join(["".join(summary[(2 * i):min(2 * (i + 1), numChunks + 1)]) for i in range(numChunks / 2 + numChunks % 2)])
    print ""
    print "Done with a round of chunk size " + str(chunkSize) + "!"
    print quantity(summary.count('S'), "chunk") + " survived; " + \
          quantity(summary.count('-'), "chunk") + " removed."
    print quantity(atomsSurviving, atom) + " survived; " + \
          quantity(atomsRemoved, atom) + " removed."
    print "Which chunks survived: " + printableSummary
    print ""

    writeTestcaseTemp("did-round-" + str(chunkSize), True)

    return (chunksRemoved > 0)


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
def minimizeBalancedPairs():
    origNumParts = len(parts)
    chunkSize = min(minimizeMax, largestPowerOfTwoSmallerThan(origNumParts))
    finalChunkSize = max(minimizeMin, 1)

    while 1:
        anyChunksRemoved = tryRemovingBalancedPairs(chunkSize)

        last = (chunkSize <= finalChunkSize)

        if anyChunksRemoved and (minimizeRepeat == "always" or (minimizeRepeat == "last" and last)):
            # Repeat with the same chunk size
            pass
        elif last:
            # Done
            break
        else:
            # Continue with the next smaller chunk size
            chunkSize /= 2

    writeTestcase(testcaseFilename)

    print "=== LITHIUM SUMMARY ==="
    if finalChunkSize == 1 and minimizeRepeat != "never":
        print "  Removing any single " + atom + " from the final file makes it uninteresting!"

    print "  Initial size: " + quantity(origNumParts, atom)
    print "  Final size: " + quantity(len(parts), atom)
    print "  Tests performed: " + str(testCount)
    print "  Test total: " + quantity(testTotal, atom)


def list_fiveParts(list, step, f, s, t):
    return (list[:f], list[f:s], list[s:(s+step)], list[(s+step):(t+step)], list[(t+step):])


def tryRemovingBalancedPairs(chunkSize):
    """Make a single run through the testcase, trying to remove chunks of size chunkSize.

    Returns True iff any chunks were removed."""

    global parts

    chunksSoFar = 0
    summary = ""

    chunksRemoved = 0
    chunksSurviving = 0
    atomsRemoved = 0

    atomsInitial = len(parts)
    numChunks = divideRoundingUp(len(parts), chunkSize)

    # Not enough chunks to remove surrounding blocks.
    if numChunks < 2:
        return False

    print "Starting a round with chunks of " + quantity(chunkSize, atom) + "."

    summary = ['S' for i in range(numChunks)]
    curly = [(parts[i].count('{') - parts[i].count('}')) for i in range(numChunks)]
    square = [(parts[i].count('[') - parts[i].count(']')) for i in range(numChunks)]
    normal = [(parts[i].count('(') - parts[i].count(')')) for i in range(numChunks)]
    chunkStart = 0
    lhsChunkIdx = 0

    try:
        while chunkStart < len(parts):

            description = "chunk #" + str(lhsChunkIdx) + "".join([" " for i in range(len(str(lhsChunkIdx)) + 4)])
            description += " of " + str(numChunks) + " chunks of size " + str(chunkSize)

            assert summary[:lhsChunkIdx].count('S') * chunkSize == chunkStart, "the chunkStart should correspond to the lhsChunkIdx modulo the removed chunks."

            chunkLhsStart = chunkStart
            chunkLhsEnd = min(len(parts), chunkLhsStart + chunkSize)

            nCurly = curly[lhsChunkIdx]
            nSquare = square[lhsChunkIdx]
            nNormal = normal[lhsChunkIdx]

            # If the chunk is already balanced, try to remove it.
            if nCurly == 0 and nSquare == 0 and nNormal == 0:
                if interesting(parts[:chunkLhsStart] + parts[chunkLhsEnd:]):
                    print "Yay, reduced it by removing " + description + " :)"
                    chunksRemoved += 1
                    atomsRemoved += (chunkLhsEnd - chunkLhsStart)
                    summary[lhsChunkIdx] = '-'
                else:
                    print "Removing " + description + " made the file 'uninteresting'."
                    chunkStart += chunkSize
                lhsChunkIdx = list_nindex(summary, lhsChunkIdx, 'S')
                continue

            # Otherwise look for the corresponding chunk.
            rhsChunkIdx = lhsChunkIdx
            for item in summary[(lhsChunkIdx + 1):]:
                rhsChunkIdx += 1
                if item != 'S':
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
                print "Skipping " + description + " because it is 'uninteresting'."
                chunkStart += chunkSize
                lhsChunkIdx = list_nindex(summary, lhsChunkIdx, 'S')
                continue

            # Otherwise we do have a match and we check if this is interesting to remove both.
            chunkRhsStart = chunkLhsStart + chunkSize * summary[lhsChunkIdx:rhsChunkIdx].count('S')
            chunkRhsStart = min(len(parts), chunkRhsStart)
            chunkRhsEnd = min(len(parts), chunkRhsStart + chunkSize)

            description = "chunk #" + str(lhsChunkIdx) + " & #" + str(rhsChunkIdx)
            description += " of " + str(numChunks) + " chunks of size " + str(chunkSize)

            if interesting(parts[:chunkLhsStart] + parts[chunkLhsEnd:chunkRhsStart] + parts[chunkRhsEnd:]):
                print "Yay, reduced it by removing " + description + " :)"
                chunksRemoved += 2
                atomsRemoved += (chunkLhsEnd - chunkLhsStart)
                atomsRemoved += (chunkRhsEnd - chunkRhsStart)
                summary[lhsChunkIdx] = '-'
                summary[rhsChunkIdx] = '-'
                lhsChunkIdx = list_nindex(summary, lhsChunkIdx, 'S')
                continue

            # Removing the braces make the failure disappear.  As we are looking
            # for removing chunk (braces), we need to make the content within
            # the braces as minimal as possible, so let us try to see if we can
            # move the chunks outside the braces.
            print "Removing " + description + " made the file 'uninteresting'."

            # Moving chunks is still a bit experimental, and it can introduce reducing loops.
            # If you want to try it, just replace this True by a False.
            if True:
                chunkStart += chunkSize
                lhsChunkIdx = list_nindex(summary, lhsChunkIdx, 'S')
                continue

            origChunkIdx = lhsChunkIdx
            stayOnSameChunk = False
            chunkMidStart = chunkLhsEnd
            midChunkIdx = list_nindex(summary, lhsChunkIdx, 'S')
            while chunkMidStart < chunkRhsStart:
                assert summary[:midChunkIdx].count('S') * chunkSize == chunkMidStart, "the chunkMidStart should correspond to the midChunkIdx modulo the removed chunks."
                description = "chunk #" + str(midChunkIdx) + "".join([" " for i in range(len(str(lhsChunkIdx)) + 4)])
                description += " of " + str(numChunks) + " chunks of size " + str(chunkSize)

                chunkMidEnd = chunkMidStart + chunkSize
                p = list_fiveParts(parts, chunkSize, chunkLhsStart, chunkMidStart, chunkRhsStart)

                nCurly = curly[midChunkIdx]
                nSquare = square[midChunkIdx]
                nNormal = normal[midChunkIdx]
                if nCurly != 0 or nSquare != 0 or nNormal != 0:
                    print "Keepping " + description + " because it is 'uninteresting'."
                    chunkMidStart += chunkSize
                    midChunkIdx = list_nindex(summary, midChunkIdx, 'S')
                    continue

                # Try moving the chunk after.
                if interesting(p[0] + p[1] + p[3] + p[2] + p[4]):
                    print "->Moving " + description + " kept the file 'interesting'."
                    chunkRhsStart -= chunkSize
                    chunkRhsEnd -= chunkSize
                    tS = list_fiveParts(summary, 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                    tc = list_fiveParts(curly  , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                    ts = list_fiveParts(square , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                    tn = list_fiveParts(normal , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                    summary = tS[0] + tS[1] + tS[3] + tS[2] + tS[4]
                    curly =   tc[0] + tc[1] + tc[3] + tc[2] + tc[4]
                    square =  ts[0] + ts[1] + ts[3] + ts[2] + ts[4]
                    normal =  tn[0] + tn[1] + tn[3] + tn[2] + tn[4]
                    rhsChunkIdx -= 1
                    midChunkIdx = summary[midChunkIdx:].index('S') + midChunkIdx
                    continue

                # Try moving the chunk before.
                if interesting(p[0] + p[2] + p[1] + p[3] + p[4]):
                    print "<-Moving " + description + " kept the file 'interesting'."
                    chunkLhsStart += chunkSize
                    chunkLhsEnd += chunkSize
                    chunkMidStart += chunkSize
                    tS = list_fiveParts(summary, 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                    tc = list_fiveParts(curly  , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                    ts = list_fiveParts(square , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                    tn = list_fiveParts(normal , 1, lhsChunkIdx, midChunkIdx, rhsChunkIdx)
                    summary = tS[0] + tS[2] + tS[1] + tS[3] + tS[4]
                    curly =   tc[0] + tc[2] + tc[1] + tc[3] + tc[4]
                    square =  ts[0] + ts[2] + ts[1] + ts[3] + ts[4]
                    normal =  tn[0] + tn[2] + tn[1] + tn[3] + tn[4]
                    lhsChunkIdx += 1
                    midChunkIdx = list_nindex(summary, midChunkIdx, 'S')
                    stayOnSameChunk = True
                    continue

                print "..Moving " + description + " made the file 'uninteresting'."
                chunkMidStart += chunkSize
                midChunkIdx = list_nindex(summary, midChunkIdx, 'S')

            lhsChunkIdx = origChunkIdx
            if not stayOnSameChunk:
                chunkStart += chunkSize
                lhsChunkIdx = list_nindex(summary, lhsChunkIdx, 'S')


    except ValueError:
        # This is a valid loop exit point.
        chunkStart = len(parts)

    atomsSurviving = atomsInitial - atomsRemoved
    printableSummary = " ".join(["".join(summary[(2 * i):min(2 * (i + 1), numChunks + 1)]) for i in range(numChunks / 2 + numChunks % 2)])
    print ""
    print "Done with a round of chunk size " + str(chunkSize) + "!"
    print quantity(summary.count('S'), "chunk") + " survived; " + \
          quantity(summary.count('-'), "chunk") + " removed."
    print quantity(atomsSurviving, atom) + " survived; " + \
          quantity(atomsRemoved, atom) + " removed."
    print "Which chunks survived: " + printableSummary
    print ""

    writeTestcaseTemp("did-round-" + str(chunkSize), True)

    return (chunksRemoved > 0)


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
def replacePropertiesByGlobals():
    origNumParts = len(parts)
    chunkSize = min(minimizeMax, 2 * largestPowerOfTwoSmallerThan(origNumParts))
    finalChunkSize = max(minimizeMin, 1)

    origNumChars = 0
    for line in parts:
        origNumChars += len(line)

    numChars = origNumChars
    while 1:
        numRemovedChars = tryMakingGlobals(chunkSize, numChars)
        numChars -= numRemovedChars

        last = (chunkSize <= finalChunkSize)

        if numRemovedChars and (minimizeRepeat == "always" or (minimizeRepeat == "last" and last)):
            # Repeat with the same chunk size
            pass
        elif last:
            # Done
            break
        else:
            # Continue with the next smaller chunk size
            chunkSize /= 2

    writeTestcase(testcaseFilename)

    print "=== LITHIUM SUMMARY ==="
    if finalChunkSize == 1 and minimizeRepeat != "never":
        print "  Removing any single " + atom + " from the final file makes it uninteresting!"

    print "  Initial size: " + quantity(origNumChars, "character")
    print "  Final size: " + quantity(numChars, "character")
    print "  Tests performed: " + str(testCount)
    print "  Test total: " + quantity(testTotal, atom)


def tryMakingGlobals(chunkSize, numChars):
    """Make a single run through the testcase, trying to remove chunks of size chunkSize.

    Returns True iff any chunks were removed."""

    global parts

    summary = ""

    numRemovedChars = 0
    numChunks = divideRoundingUp(len(parts), chunkSize)
    finalChunkSize = max(minimizeMin, 1)

    # Map words to the chunk indexes in which they are present.
    words = {}
    for chunk, line in enumerate(parts):
        for match in re.finditer(r'(?<=[\w\d_])\.(\w+)', line):
            word = match.group(1)
            if not word in words:
                words[word] = [chunk]
            else:
                words[word] += [chunk]

    # All patterns have been removed sucessfully.
    if len(words) == 0:
        return 0

    print "Starting a round with chunks of " + quantity(chunkSize, atom) + "."
    summary = ['S' for i in range(numChunks)]

    for word, chunks in words.items():
        chunkIndexes = {}
        for chunkStart in chunks:
            chunkIdx = int(chunkStart / chunkSize)
            if not chunkIdx in chunkIndexes:
                chunkIndexes[chunkIdx] = [chunkStart]
            else:
                chunkIndexes[chunkIdx] += [chunkStart]

        for chunkIdx, chunkStarts in chunkIndexes.items():
            # Unless this is the final size, let's try to remove couple of
            # prefixes, otherwise wait for the final size to remove each of them
            # individually.
            if len(chunkStarts) == 1 and finalChunkSize != chunkSize:
                continue

            description = "'" + word + "' in "
            description += "chunk #" + str(chunkIdx) + " of " + str(numChunks) + " chunks of size " + str(chunkSize)

            maybeRemoved = 0
            newParts = parts
            for chunkStart in chunkStarts:
                subst = re.sub("[\w_.]+\." + word, word, newParts[chunkStart])
                maybeRemoved += len(newParts[chunkStart]) - len(subst)
                newParts = newParts[:chunkStart] + [ subst ] + newParts[(chunkStart+1):]

            if interesting(newParts):
                print "Yay, reduced it by removing prefixes of " + description + " :)"
                numRemovedChars += maybeRemoved
                summary[chunkIdx] = 's'
                words[word] = [ c for c in chunks if c not in chunkIndexes ]
                if len(words[word]) == 0:
                    del words[word]
            else:
                print "Removing prefixes of " + description + " made the file 'uninteresting'."

    numSurvivingChars = numChars - numRemovedChars
    printableSummary = " ".join(["".join(summary[(2 * i):min(2 * (i + 1), numChunks + 1)]) for i in range(numChunks / 2 + numChunks % 2)])
    print ""
    print "Done with a round of chunk size " + str(chunkSize) + "!"
    print quantity(summary.count('S'), "chunk") + " survived; " + \
          quantity(summary.count('s'), "chunk") + " shortened."
    print quantity(numSurvivingChars, "character") + " survived; " + \
          quantity(numRemovedChars, "character") + " removed."
    print "Which chunks survived: " + printableSummary
    print ""

    writeTestcaseTemp("did-round-" + str(chunkSize), True)

    return numRemovedChars


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
def replaceArgumentsByGlobals():
    roundNum = 0
    while 1:
        numRemovedArguments = tryArgumentsAsGlobals(roundNum)
        roundNum += 1

        if numRemovedArguments and (minimizeRepeat == "always" or minimizeRepeat == "last"):
            # Repeat with the same chunk size
            pass
        else:
            # Done
            break

    writeTestcase(testcaseFilename)

    print "=== LITHIUM SUMMARY ==="
    print "  Tests performed: " + str(testCount)
    print "  Test total: " + quantity(testTotal, atom)


def tryArgumentsAsGlobals(roundNum):
    """Make a single run through the testcase, trying to remove chunks of size chunkSize.
    
    Returns True iff any chunks were removed."""

    global parts

    numMovedArguments = 0
    numSurvivedArguments = 0

    # Map words to the chunk indexes in which they are present.
    functions = {}
    anonymousQueue = []
    anonymousStack = []
    for chunk, line in enumerate(parts):
        # Match function definition with at least one argument.
        for match in re.finditer(r'(?:function\s+(\w+)|(\w+)\s*=\s*function)\s*\((\s*\w+\s*(?:,\s*\w+\s*)*)\)', line):
            fun = match.group(1)
            if fun is None:
                fun = match.group(2)

            if match.group(3) == "":
                args = []
            else:
                args = match.group(3).split(',')

            if not fun in functions:
                functions[fun] = { "defs": args, "argsPattern": match.group(3), "chunk": chunk, "uses": [] }
            else:
                functions[fun]["defs"] = args
                functions[fun]["argsPattern"] = match.group(3)
                functions[fun]["chunk"] = chunk


        # Match anonymous function definition, which are surrounded by parentheses.
        for match in re.finditer(r'\(function\s*\w*\s*\(((?:\s*\w+\s*(?:,\s*\w+\s*)*)?)\)\s*{', line):
            if match.group(1) == "":
                args = []
            else:
                args = match.group(1).split(',')
            anonymousStack += [{ "defs": args, "chunk": chunk, "use": None, "useChunk": 0 }]

        # Match calls of anonymous function.
        for match in re.finditer(r'}\s*\)\s*\(((?:[^()]|\([^,()]*\))*)\)', line):
            if len(anonymousStack) == 0:
                continue
            anon = anonymousStack[-1]
            anonymousStack = anonymousStack[:-1]
            if match.group(1) == "" and len(anon["defs"]) == 0:
                continue
            if match.group(1) == "":
                args = []
            else:
                args = match.group(1).split(',')
            anon["use"] = args
            anon["useChunk"] = chunk
            anonymousQueue += [anon]

        # match function calls. (and some definitions)
        for match in re.finditer(r'((\w+)\s*\(((?:[^()]|\([^,()]*\))*)\))', line):
            pattern = match.group(1)
            fun = match.group(2)
            if match.group(3) == "":
                args = []
            else:
                args = match.group(3).split(',')
            if not fun in functions:
                functions[fun] = { "uses": [] }
            functions[fun]["uses"] += [{ "values": args, "chunk": chunk, "pattern": pattern }]


    # All patterns have been removed sucessfully.
    if len(functions) == 0 and len(anonymousQueue) == 0:
        return 0

    print "Starting removing function arguments."

    for fun, argsMap in functions.items():
        description = "arguments of '" + fun + "'"
        if "defs" not in argsMap or len(argsMap["uses"]) == 0:
            print "Ignoring " + description + " because it is 'uninteresting'."
            continue

        maybeMovedArguments = 0
        newParts = parts

        # Remove the function definition arguments
        argDefs = argsMap["defs"]
        defChunk = argsMap["chunk"]
        subst = string.replace(newParts[defChunk], argsMap["argsPattern"], "", 1)
        newParts = newParts[:defChunk] + [ subst ] + newParts[(defChunk+1):]

        # Copy callers arguments to globals.
        for argUse in argsMap["uses"]:
            values = argUse["values"]
            chunk = argUse["chunk"]
            if chunk == defChunk and values == argDefs:
                continue
            while len(values) < len(argDefs):
                values = values + ["undefined"]
            setters = "".join([ a + " = " + v + ";\n" for a, v in zip(argDefs, values) ])
            subst = setters + newParts[chunk]
            newParts = newParts[:chunk] + [ subst ] + newParts[(chunk+1):]
        maybeMovedArguments += len(argDefs)

        if interesting(newParts):
            print "Yay, reduced it by removing " + description + " :)"
            numMovedArguments += maybeMovedArguments
        else:
            numSurvivedArguments += maybeMovedArguments
            print "Removing " + description + " made the file 'uninteresting'."

        for argUse in argsMap["uses"]:
            chunk = argUse["chunk"]
            values = argUse["values"]
            if chunk == defChunk and values == argDefs:
                continue

            newParts = parts
            subst = string.replace(newParts[chunk], argUse["pattern"], fun + "()", 1)
            if newParts[chunk] == subst:
                continue
            newParts = newParts[:chunk] + [ subst ] + newParts[(chunk+1):]
            maybeMovedArguments = len(values)

            descriptionChunk = description + " at " + atom + " #" + str(chunk)
            if interesting(newParts):
                print "Yay, reduced it by removing " + descriptionChunk + " :)"
                numMovedArguments += maybeMovedArguments
            else:
                numSurvivedArguments += maybeMovedArguments
                print "Removing " + descriptionChunk + " made the file 'uninteresting'."

    # Remove immediate anonymous function calls.
    for anon in anonymousQueue:
        noopChanges = 0
        maybeMovedArguments = 0
        newParts = parts

        argDefs = anon["defs"]
        defChunk = anon["chunk"]
        values = anon["use"]
        chunk = anon["useChunk"]
        description = "arguments of anonymous function at #" + atom + " " + str(defChunk)

        # Remove arguments of the function.
        subst = string.replace(newParts[defChunk], ",".join(argDefs), "", 1)
        if newParts[defChunk] == subst:
            noopChanges += 1
        newParts = newParts[:defChunk] + [ subst ] + newParts[(defChunk+1):]

        # Replace arguments by their value in the scope of the function.
        while len(values) < len(argDefs):
            values = values + ["undefined"]
        setters = "".join([ "var " + a + " = " + v + ";\n" for a, v in zip(argDefs, values) ])
        subst = newParts[defChunk] + "\n" + setters
        if newParts[defChunk] == subst:
            noopChanges += 1
        newParts = newParts[:defChunk] + [ subst ] + newParts[(defChunk+1):]

        # Remove arguments of the anonymous function call.
        subst = string.replace(newParts[chunk], ",".join(anon["use"]), "", 1)
        if newParts[chunk] == subst:
            noopChanges += 1
        newParts = newParts[:chunk] + [ subst ] + newParts[(chunk+1):]
        maybeMovedArguments += len(values)

        if noopChanges == 3:
            continue

        if interesting(newParts):
            print "Yay, reduced it by removing " + description + " :)"
            numMovedArguments += maybeMovedArguments
        else:
            numSurvivedArguments += maybeMovedArguments
            print "Removing " + description + " made the file 'uninteresting'."


    print ""
    print "Done with this round!"
    print quantity(numMovedArguments, "argument") + " moved;"
    print quantity(numSurvivedArguments, "argument") + " survived."

    writeTestcaseTemp("did-round-" + str(roundNum), True)

    return numMovedArguments


# Helpers
def divideRoundingUp(n, d):
    return (n // d) + (1 if n % d != 0 else 0)


def isPowerOfTwo(n):
    i = 1
    while True:
        if i == n:
            return True
        if i > n:
            return False
        i *= 2


def largestPowerOfTwoSmallerThan(n):
    i = 1
    while True:
        if i * 2 >= n:
            return i
        i *= 2


def quantity(n, s):
    """Convert a quantity to a string, with correct pluralization."""
    r = str(n) + " " + s
    if n != 1:
        r += "s"
    return r


if __name__ == "__main__":
    if processOptions():
        main()
