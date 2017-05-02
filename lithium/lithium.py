#!/usr/bin/env python
# coding=utf-8

import argparse
import logging
import os
import time
import sys


log = logging.getLogger("lithium") # pylint: disable=invalid-name


class LithiumError(Exception):
    pass


class Testcase(object):

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
                    raise LithiumError("The testcase (%s) has a line containing 'DDEND' without a line containing 'DDBEGIN' before it.", self.filename)
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
            raise LithiumError("The testcase (%s) has a line containing 'DDBEGIN' but no line containing 'DDEND'.", self.filename)

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

        if len(self.parts) > 0:
            # Move the line break at the end of the last line out of the reducible
            # part so the "DDEND" line doesn't get combined with another line.
            self.parts.pop()
            self.after = "\n" + self.after


    def readTestcaseLine(self, line):
        for char in line:
            self.parts.append(char)


class Strategy(object):
    """
    Minimization strategy

    This should implement a main() method which takes a testcase and calls the interesting callback repeatedly to minimize the testcase.
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
            help="For the first round only, start n chars/lines into the file. Best for max to divide n. [Mostly intended for internal use]")
        grp_add.add_argument(
            "--repeatfirstround", action="store_true",
            help="Treat the first round as if it removed chunks; possibly repeat it.  [Mostly intended for internal use]")
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

    # Main reduction algorithm
    def main(self, testcase, interesting, tempFilename):
        log.info("The original testcase has %s.", quantity(len(testcase.parts), testcase.atom))
        log.info("Checking that the original testcase is 'interesting'...")
        if not interesting(testcase, writeIt=False):
            log.info("Lithium result: the original testcase is not 'interesting'!")
            return 1

        if len(testcase.parts) == 0:
            log.info("The file has %s so there's nothing for Lithium to try to remove!", quantity(0, testcase.atom))

        testcase.writeTestcase(tempFilename("original", False))

        origNumParts = len(testcase.parts)
        chunkSize = min(self.minimizeMax, largestPowerOfTwoSmallerThan(origNumParts))
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
                last = (chunkSize == finalChunkSize)
                empty = (len(testcase.parts) == 0)
                log.info("")
                if not empty and anyChunksRemoved and (self.minimizeRepeat == "always" or (self.minimizeRepeat == "last" and last)):
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
            description = "Removing a chunk of size %d starting at %d of %d" % (chunkSize, chunkStart, len(testcase.parts))
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

        testcase.writeTestcase()

        summaryHeader()

        if chunkSize == 1 and not anyChunksRemoved and self.minimizeRepeat != "never":
            log.info("  Removing any single %s from the final file makes it uninteresting!", testcase.atom)

        log.info("  Initial size: %s", quantity(origNumParts, testcase.atom))
        log.info("  Final size: %s", quantity(len(testcase.parts), testcase.atom))

        return 0


class Lithium(object):

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


    def main(self):
        logging.basicConfig(format="%(message)s", level=logging.INFO)
        self.processArgs()

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


    def processArgs(self):
        # Build list of strategies and testcase types
        strategies = {}
        testcaseTypes = {}
        for cls in globals().values():
            if isinstance(cls, type):
                if cls is not Strategy and issubclass(cls, Strategy):
                    assert cls.name not in strategies
                    strategies[cls.name] = cls
                elif cls is not Testcase and issubclass(cls, Testcase):
                    assert cls.atom not in testcaseTypes
                    testcaseTypes[cls.atom] = cls

        # Try to parse --conflict before anything else
        class ArgParseTry(argparse.ArgumentParser):
            def exit(subself, **kwds): # pylint: disable=no-self-argument
                pass
            def error(subself, message): # pylint: disable=no-self-argument
                pass

        defaultStrategy = "minimize"
        assert defaultStrategy in strategies
        parser = ArgParseTry(add_help=False)
        parser.add_argument(
            "--strategy",
            default=defaultStrategy,
            choices=strategies.keys())
        args = parser.parse_known_args()
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
            "-c", "--char",
            action="store_true",
            help="Don't treat lines as atomic units; treat the file as a sequence of characters rather than a sequence of lines.")
        grp_opt.add_argument(
            "--strategy",
            default=self.strategy.name, # this has already been parsed above, it's only here for the help message
            choices=strategies.keys(),
            help="reduction strategy to use. default: %s" % defaultStrategy)
        self.strategy.addArgs(parser)
        grp_ext = parser.add_argument_group(description="Condition, condition options and file-to-reduce")
        grp_ext.add_argument(
            "extra_args",
            action="append",
            nargs=argparse.REMAINDER,
            help="condition [condition options] file-to-reduce")

        args = parser.parse_args()
        self.strategy.processArgs(parser, args)

        self.tempDir = args.tempdir
        atom = "char" if args.char else "line"
        extra_args = args.extra_args[0]

        if args.testcase:
            testcaseFilename = args.testcase
        elif len(extra_args) > 0:
            testcaseFilename = extra_args[-1]  # can be overridden by --testcase in processOptions
        else:
            parser.error("No testcase specified (use --testcase or last condition arg)")
        self.testcase = testcaseTypes[atom]()
        self.testcase.readTestcase(testcaseFilename)

        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "interestingness")))
        import ximport # pylint: disable=import-error

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


def isPowerOfTwo(n):
    return (1<<(n.bit_length() - 1)) == n


def largestPowerOfTwoSmallerThan(n):
    return 1<<(n.bit_length() - 2)


def quantity(n, unit):
    "Convert a quantity to a string, with correct pluralization."
    r = "%d %s" % (n, unit)
    if n != 1:
        r += "s"
    return r


if __name__ == "__main__":
    exit(Lithium().main())
