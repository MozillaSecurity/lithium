#!/usr/bin/env python
import getopt, sys, os, subprocess, time

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
* --strategy=[minimize, remove-pair, remove-substring, check-only].
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
        # XXX Consider using optparse (with disable_interspersed_args)
        opts, args = getopt.getopt(sys.argv[1:], "hc", ["help", "char", "strategy=", "repeat=", "min=", "max=", "chunksize=", "chunkstart=", "testcase=", "tempdir=", "repeatfirstround", "maxruntime="])
    except getopt.GetoptError, exc:
        usageError(exc.msg)
        
    allPositionalArgs = args

    if len(args) == 0:
        # No arguments; not even a condition was specified
        usage()
        sys.exit(0)

    if len(args) > 1:
        testcaseFilename = args[-1] # can be overridden by --testcase in processOptions
        
    processOptions(opts)

    if testcaseFilename == None:
        usageError("No testcase specified (use --testcase or last condition arg)")

    conditionScript = importRelativeOrAbsolute(args[0])
    conditionArgs = args[1:]

    if hasattr(conditionScript, "init"):
        conditionScript.init(conditionArgs)

    e = testcaseFilename.rsplit(".", 1)
    if len(e) > 1:
        testcaseExtension = "." + e[1]


    readTestcase()

    if tempDir == None:
        createTempDir()
        print "Intermediate files will be stored in " + tempDir + os.sep + "."

    if strategy == "check-only":
        r = interesting(parts, writeIt=False)
        print 'Lithium result: ' + ('interesting.' if r else 'not interesting.')
        sys.exit(0)

    strategyFunction = {
        'minimize': minimize,
        'remove-pair': tryRemovingPair,
        'remove-adjacent-pairs': tryRemovingAdjacentPairs,
        'remove-substring': tryRemovingSubstring
    }.get(strategy, None)

    if not strategyFunction:
        usageError("Unknown strategy!")

    print "The original testcase has " + quantity(len(parts), atom) + "."
    print "Checking that the original testcase is 'interesting'..."
    if not interesting(parts, writeIt=False):
        print "Lithium result: the original testcase is not 'interesting'!"
        sys.exit(0)

    if len(parts) == 0:
        usageError("The file has " + quantity(0, atom) + " so there's nothing for Lithium to try to remove!")

    writeTestcaseTemp("original", False)
    strategyFunction()


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
    sys.exit(2)


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
    file = open(filename, "w")
    file.write(before)
    for i in range(len(parts)):
        file.write(parts[i])
    file.write(after)
    file.close()

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
    finalChunkSize = max(minimizeMin, 1)
    chunkStart = minimizeChunkStart
    anyChunksRemoved = minimizeRepeatFirstRound
    
    while True:
        if stopAfterTime != None and time.time() > stopAfterTime:
            # Not all switches will be copied!  Be sure to add --tempdir, --maxruntime if desired.
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


def tryRemovingChunks(chunkSize):
    
    print "Done with a round of chunk size " + str(chunkSize) + "!"
    return anyChunksRemoved
    
    

# Other reduction algorithms
# (Use these if you're really frustrated with something you know is 1-minimal.)

def tryRemovingAdjacentPairs():
    # XXX capture the idea that after removing (4,5) it might be sensible to remove (3,6)
    # but also that after removing (2,3) and (4,5) it might be sensible to remove (1,6)
    # XXX also want to remove three at a time, and two at a time that are one line apart
    for i in range(0, numParts - 2):
        if enabled[i]:
            enabled[i] = False
            enabled[i + 1] = False
            if interesting():
                print "Removed an adjacent pair based at " + str(i)
            else:
                enabled[i] = True
                enabled[i + 1] = True
    # Restore the original testcase
    writeTestcase(testcaseFilename)
    print "Done with one pass of removing adjacent pairs"



def tryRemovingPair():
    for i in range(0, numParts):
        enabled[i] = False
        for j in range(i + 1, numParts):
            enabled[j] = False
            print "Trying removing the pair " + str(i) + ", " + str(j)
            if interesting():
                print "Success!  Removed a pair!  Exiting."
                sys.exit(0)
            enabled[j] = True
        enabled[i] = True

    # Restore the original testcase
    writeTestcase(testcaseFilename)
    print "Failure!  No pair can be removed."
            

def tryRemovingSubstring():
    for i in range(0, numParts):
        for j in range(i, numParts):
            enabled[j] = False
            print "Trying removing the substring " + str(i) + ".." + str(j)
            if interesting():
                print "Success!  Removed a substring!  Exiting."
                sys.exit(0)
        for j in range(i, numParts):
            enabled[j] = True

    # Restore the original testcase
    writeTestcase(testcaseFilename)
    print "Failure!  No substring can be removed."
    

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

def importRelativeOrAbsolute(f):
    # maybe there's a way to do this more sanely with the |imp| module...
    if f.endswith(".py"):
        f = f[:-3]
    p, f = os.path.split(f)
    if p:
        # Add the path part of the given filename to the import path
        sys.path.append(p)
    else:
        # Add working directory to the import path
        sys.path.append(".")
    module = __import__(f)
    sys.path.pop()
    return module

# Run main

if __name__ == "__main__":
    main()
