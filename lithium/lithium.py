#!/usr/bin/env python

import argparse
import os
import time
import sys

path0 = os.path.dirname(os.path.abspath(__file__))
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
stopAfterTime = None


# Main and friends

def main():
    global conditionScript, conditionArgs, testcaseFilename, testcaseExtension, strategy, parts

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
            'minimize': minimize
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
        "--strategy",
        default="minimize",
        choices=["minimize", "check-only"],
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
        repeat = "last"
    else:
        minimizeMin = args.min
        minimizeMax = args.max
        repeat = args.repeat
    minimizeChunkStart = args.chunkstart
    minimizeRepeatFirstRound = args.repeatfirstround
    if args.maxruntime:
        stopAfterTime = time.time() + args.maxruntime
    extra_args = args.extra_args[0]

    if args.testcase is not None:
        testcaseFilename = args.testcase
    elif len(extra_args) > 0:
        testcaseFilename = extra_args[-1] # can be overridden by --testcase in processOptions
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
            print "Lithium result: please perform another pass using the same arguments"
            break

        if chunkStart >= len(parts):
            writeTestcaseTemp("did-round-" + str(chunkSize), True)
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
    if processOptions():
        main()
