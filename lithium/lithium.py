#!/usr/bin/env python

from __future__ import with_statement

import getopt
import os
import subprocess
import time
import sys

path0 = os.path.dirname(os.path.abspath(__file__))
path1 = os.path.abspath(os.path.join(path0, os.pardir, 'interestingness'))
sys.path.append(path1)
import ximport

def usage():
    print """Lithium, an automated testcase reduction tool by Jesse Ruderman

Usage:

./lithium.py [options] condition [condition options] file-to-reduce

Example:

./lithium.py crashes 120 ~/tracemonkey/js/src/debug/js -j a.js
     Lithium will reduce a.js subject to the condition that the following
     crashes in 120 seconds:
     ~/tracemonkey/js/src/debug/js -j a.js

Options:
* --char (-c).
      Don't treat lines as atomic units; treat the file as a sequence
      of characters rather than a sequence of lines.
* --strategy=[minimize, minimize-around, minimize-balanced].
      default: minimize.
* --testcase=filename.
      default: last thing on the command line, which can double as passing in.

Additional options for the default strategy (--strategy=minimize)
* --repeat=[always, last, never]. default: last
     Whether to repeat a chunk size if chunks are removed.
* --max=n. default: about half of the file.
* --min=n. default: 1.
     What chunk sizes to test.  Must be powers of two.
* --chunksize=n
     Shortcut for "repeat=never, min=n, max=n"
* --chunkstart=n
     For the first round only, start n chars/lines into the file. Best for max to divide n.  [Mostly intended for internal use]
* --repeatfirstround
     Treat the first round as if it removed chunks; possibly repeat it.  [Mostly intended for internal use]
* --maxruntime=n
     If reduction takes more than n seconds, stop (and print instructions for continuing).

See doc/using.html for more information.

"""


# Globals

strategy = "minimize"
minimizeRepeat = "last"
minimizeMin = 1
minimizeMax = pow(2, 30)
minimizeChunkStart = 0
minimizeRepeatFirstRound = False

atom = "line"

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
allPositionalArgs = []
stopAfterTime = None


# Main and friends

def main():
    global conditionScript, conditionArgs, testcaseFilename, testcaseExtension, strategy, allPositionalArgs
    global parts

    try:
        # XXX Consider using optparse (with disable_interspersed_args) or argparse (with argparse.REMAINDER)
        opts, args = getopt.getopt(sys.argv[1:], "hc", ["help", "char", "strategy=", "repeat=", "min=", "max=", "chunksize=", "chunkstart=", "testcase=", "tempdir=", "repeatfirstround", "maxruntime="])
    except getopt.GetoptError, exc:
        usageError(exc.msg)

    allPositionalArgs = args

    if len(args) == 0:
        # No arguments; not even a condition was specified
        usage()
        return

    if len(args) > 1:
        testcaseFilename = args[-1] # can be overridden by --testcase in processOptions

    processOptions(opts)

    if testcaseFilename == None:
        usageError("No testcase specified (use --testcase or last condition arg)")

    conditionScript = ximport.importRelativeOrAbsolute(args[0])
    conditionArgs = args[1:]

    e = testcaseFilename.rsplit(".", 1)
    if len(e) > 1:
        testcaseExtension = "." + e[1]

    readTestcase()

    if hasattr(conditionScript, "init"):
        conditionScript.init(conditionArgs)

    try:

        if tempDir == None:
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


def processOptions(opts):
    global atom, strategy, testcaseFilename, tempDir
    global minimizeRepeat, minimizeMin, minimizeMax, minimizeChunkStart, minimizeRepatFirstRound, stopAfterTime

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit(0)
        elif o == "--testcase":
            testcaseFilename = a
        elif o == "--tempdir":
            tempDir = a
        elif o in ("-c", "--char"):
            atom = "char"
        elif o == "--strategy":
            strategy = a
        elif o == "--min":
            minimizeMin = int(a)
            if not isPowerOfTwo(minimizeMin):
                usageError("min must be a power of two.")
        elif o == "--max":
            minimizeMax = int(a)
            if not isPowerOfTwo(minimizeMax):
                usageError("max must be a power of two.")
        elif o == "--repeat":
            minimizeRepeat = a
            if not (minimizeRepeat in ("always", "last", "never")):
                usageError("repeat must be 'always', 'last', or 'never'.")
        elif o == "--chunksize":
            minimizeMin = int(a)
            minimizeMax = minimizeMin
            minimizeRepeat = "never"
            if not isPowerOfTwo(minimizeMin):
                usageError("Chunk size must be a power of two.")
        elif o == "--chunkstart":
            minimizeChunkStart = int(a)
        elif o == "--repeatfirstround":
            minimizeRepatFirstRound = True
        elif o == "--maxruntime":
            stopAfterTime = time.time() + int(a)


def usageError(s):
    print "=== LITHIUM SUMMARY ==="
    print s
    raise Exception(s)


# Functions for manipulating the testcase (aka the 'interesting' file)

def readTestcase():
    hasDDSection = False

    try:
        file = open(testcaseFilename, "r")
    except IOError:
        usageError("Can't read the original testcase file, " + testcaseFilename + "!")

    # Determine whether the file has a DDBEGIN..DDEND section.
    for line in file:
        if line.find("DDEND") != -1:
            usageError("The testcase (" + testcaseFilename + ") has a line containing 'DDEND' without a line containing 'DDBEGIN' before it.")
        if line.find("DDBEGIN") != -1:
            hasDDSection = True
            break

    file.seek(0)

    if hasDDSection:
        # Reduce only the part of the file between 'DDBEGIN' and 'DDEND',
        # leaving the rest unchanged.
        #print "Testcase has a DD section"
        readTestcaseWithDDSection(file)
    else:
        # Reduce the entire file.
        #print "Testcase does not have a DD section"
        for line in file:
            readTestcaseLine(line)

    file.close()


def readTestcaseWithDDSection(file):
    global before, after
    global parts

    for line in file:
        before += line
        if line.find("DDBEGIN") != -1:
            break

    for line in file:
        if line.find("DDEND") != -1:
            after += line
            break
        readTestcaseLine(line)
    else:
        usageError("The testcase (" + testcaseFilename + ") has a line containing 'DDBEGIN' but no line containing 'DDEND'.")

    for line in file:
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

def writeTestcase(filename):
    with open(filename, "w") as file:
        file.write(before)
        for i in range(len(parts)):
            file.write(parts[i])
        file.write(after)

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
        except OSError, e:
            i += 1


# If the file is still interesting after the change, changes the global "parts" and returns True.
def interesting(partsSuggestion, writeIt=True):
    global tempFileCount, testcaseFilename, conditionArgs
    global testCount, testTotal
    global parts
    oldParts = parts # would rather be less side-effecty about this, and be passing partsSuggestion around
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
    if tempDir != None:
        tempFileTag = "interesting" if inter else "boring"
        writeTestcaseTemp(tempFileTag, True)

    if not inter:
        parts = oldParts
    return inter


# Main reduction algorithm

#
# This Strategy attempt at removing chuncks which might not be interesting
# code, but which be removed independently of any other.  This happens
# frequently with values which are computed, but either after the execution,
# or never used to influenced the interesting part.
#
#   a = compute();
#   b = compute();   <-- !!!
#   intereting(a);
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
        if stopAfterTime != None and time.time() > stopAfterTime:
            # Not all switches will be copied!  Be sure to add --tempdir, --maxruntime if desired.
            # Not using shellify() here because of the strange requirements of bot.py's lithium-command.txt.
            print "Lithium result: please continue using: " + " ".join(
                 [
                 #"--testcase=" + testcaseFilename,
                 "--max=" + str(chunkSize),
                 "--chunkstart=" + str(chunkStart)] +
                (["--repeatfirstround"] if anyChunksRemoved else []) +
                (["--char"] if atom == "char" else []) +
                allPositionalArgs
                )
            break

        if chunkStart >= len(parts):
            writeTestcaseTemp("did-round-" + str(chunkSize), True);
            last = (chunkSize == finalChunkSize)
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



#
# This Strategy attempt at removing pairs of chuncks which might be surrounding
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
        anyChunksRemoved = tryRemovingSurroundingChunks(chunkSize);

        last = (chunkSize == finalChunkSize)

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

    writeTestcaseTemp("did-round-" + str(chunkSize), True);

    return (chunksRemoved > 0)


#
# This Strategy attempt at removing balanced chuncks which might be surrounding
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
        anyChunksRemoved = tryRemovingBalancedPairs(chunkSize);

        last = (chunkSize == finalChunkSize)

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

    writeTestcaseTemp("did-round-" + str(chunkSize), True);

    return (chunksRemoved > 0)



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

# Run main

if __name__ == "__main__":
    main()
