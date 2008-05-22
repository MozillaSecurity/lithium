#!/usr/bin/env python
import getopt, sys, os, subprocess

def usage():
    print """Lithium, an automated testcase reduction tool by Jesse Ruderman
    
Usage:
    
./lith.py [options] test file [test parameters]

* test: an 'interestingness test' script
     It must return 0 for "interesting" and nonzero for "uninteresting".
* file: an 'interesting' file you would like reduced
     If it has lines containing "DDBEGIN" and "DDEND", Lithium will
     only reduce the section between those lines.
* test parameters: extra command-line arguments to pass to the test

Options:
* --char (-c).
    Don't treat lines as atomic units; treat the file as a sequence
    of characters rather than a sequence of lines.
* --strategy=[minimize, remove-pair, remove-substring]. default: minimize.

Additional options for the default strategy (--strategy=minimize)
* --repeat=[always, last, never]. default: last
     Whether to repeat a chunk size if chunks are removed.
* --max=n. default: about half of the file.
* --min=n. default: 1.
     What chunk sizes to test.  Must be powers of two.
* --chunksize=n
     Shortcut for "repeat=never, min=n, max=n"

See doc/using.html for more information.

"""


# Globals

strategy = "minimize"
minimizeRepeat = "last"
minimizeMin = 1
minimizeMax = pow(2, 30)
    
atom = "line"

testFilename = None
testArgs = None
testcaseFilename = None
testcaseExtension = ""

testCount = 0
testTotal = 0

tempDir = None
tempFileCount = 0

before = ""
after = ""
parts = []
enabled = []
numParts = 0
boringnessCache = {}


# Main and friends

def main():
    global testFilename, testArgs, testcaseFilename, testcaseExtension, strategy
    global parts, numParts, enabled

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hc", ["help", "char", "strategy=", "repeat=", "min=", "max=", "chunksize="])
    except getopt.GetoptError, exc:
        usageError(exc.msg)
        
    processOptions(opts)

    if len(args) < 2:
        usageError("You need to specify a test and a file.")
        
    testFilename = args[0]
    testcaseFilename = args[1]
    testArgs = args[:] # includes the name of the test program, which subprocess.call needs anyway

    e = testcaseFilename.rsplit(".", 1)
    if len(e) > 1:
        testcaseExtension = "." + e[1]

    readTestcase()
    numParts = len(parts)
    enabled = [True for p in parts]
    
    
    print "The original testcase has " + quantity(numParts, atom) + "."
    
    print "Checking that the original testcase is 'interesting'..."
    if not interesting():
        usageError("The original testcase is not 'interesting'!")
        
    if numParts == 0:
        usageError("The file has " + quantity(0, atom) + " so there's nothing for Lithium to try to remove!")

    strategyFunction = {
        'minimize': minimize,
        'remove-pair': tryRemovingPair,
        'remove-substring': tryRemovingSubstring
    }.get(strategy, None)

    if not strategyFunction:
        usageError("Unknown strategy!")

    createTempDir()
    print "Intermediate files will be stored in " + tempDir + os.sep + "."
    writeTestcaseTemp("original", False)

    strategyFunction()


def processOptions(opts):
    global atom, minimizeRepeat, minimizeMin, minimizeMax, strategy

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit(0)
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


def usageError(s):
    print s
    print "Use --help if you need it :)"
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
    global parts, numParts, enabled
    
    if atom == "line":
       parts.append(line)
    elif atom == "char":
        for char in line:
            parts.append(char)



def writeTestcase(filename):
    global numParts
    
    file = open(filename, "w")
    file.write(before)
    for i in range(numParts):
        if enabled[i]:
            file.write(parts[i])
    file.write(after)
    file.close()
   
   
def writeTestcaseTemp(partialFilename, useNumber):
    global tempFileCount
    if useNumber:
        tempFileCount += 1
        partialFilename = str(tempFileCount) + "-" + partialFilename
    writeTestcase(tempDir + os.sep + partialFilename + testcaseExtension)


def createTempDir():
    global tempDir
    i = 1
    while 1:
        tempDir = "tmp" + str(i)
        if not os.path.exists(tempDir):
            os.mkdir(tempDir)
            break
        i += 1



# Interestingness test

def interesting():
    global tempFileCount, testcaseFilename, testArgs
    global enabled, boringnessCache
    global testCount, testTotal

    writeTestcase(testcaseFilename)
    
    # This method of creating enabledKey is more compact than str(enabled)
    enabledKey = "".join(str(int(b)) for b in enabled)  
    if enabledKey in boringnessCache:
        print "boringnessCache hit"
        return False
        
    testCount += 1
    testTotal += sum(enabled)

    try:
        status = subprocess.call(testArgs)
    except OSError, e:
        print "Lithium tried to run:"
        print "  " + repr(testArgs)
        print "but got this error:"
        print "  " + str(e)
        sys.exit(2)

    # Save an extra copy of the file inside the temp directory.
    # This is useful if you're reducing an assertion and encounter a crash:
    # it gives you a way to try to reproduce the crash.
    if tempDir != None:
        if status == 0:
          tempFileTag = "interesting"
        else:
          tempFileTag = "boring"
        writeTestcaseTemp(tempFileTag, True)

    if status != 0:
        boringnessCache[enabledKey] = True

    return status == 0


# Main reduction algorithm

def minimize():

    chunkSize = min(minimizeMax, largestPowerOfTwoSmallerThan(numParts))
    finalChunkSize = max(minimizeMin, 1)
    
    while 1:
        anyChunksRemoved = tryRemovingChunks(chunkSize);
    
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
    
    print "Lithium is done!"

    if finalChunkSize == 1 and minimizeRepeat != "never":
        print "  Removing any single " + atom + " from the final file makes it uninteresting!"

    print "  Initial size: " + quantity(numParts, atom)
    print "  Final size: " + quantity(sum(enabled), atom)
    print "  Tests performed: " + str(testCount)
    print "  Test total: " + quantity(testTotal, atom)


def tryRemovingChunks(chunkSize):
    """Make a single run through the testcase, trying to remove chunks of size chunkSize.
    
    Returns True iff any chunks were removed."""
    
    global enabled
    
    chunksSoFar = 0
    summary = ""

    chunksRemoved = 0
    chunksSurviving = 0
    atomsRemoved = 0
    atomsSurviving = 0

    print "Starting a round with chunks of " + quantity(chunkSize, atom) + "."

    for chunkStart in range(0, numParts, chunkSize):

        if not enabled[chunkStart]:
            continue

        chunkEnd = min(numParts, chunkStart + chunkSize)
        
        for pos in range(chunkStart, chunkEnd):
            enabled[pos] = False
        
        if interesting():
            print "Yay, reduced it by removing " + str(chunkStart) + ".." + str(chunkEnd - 1) + " :)"
            
            chunksRemoved += 1
            atomsRemoved += (chunkEnd - chunkStart)
            summary += '-';
        else:
            print "Removing " + str(chunkStart) + ".." + str(chunkEnd - 1) + " made the file 'uninteresting'.  Putting it back."

            chunksSurviving += 1
            atomsSurviving += (chunkEnd - chunkStart)
            summary += 'S';
    
            for pos in range(chunkStart, chunkEnd):
                enabled[pos] = True
  
        # Put a space between each pair of chunks in the summary.
        # During 'minimize', this is useful because it shows visually which 
        # chunks used to be part of a single larger chunk.
        
        chunksSoFar += 1
        if chunksSoFar % 2 == 0:
          summary += " ";
  
    print ""
    print "Done with a round of chunk size " + str(chunkSize) + "!"
    print quantity(chunksSurviving, "chunk") + " survived; " + \
          quantity(chunksRemoved, "chunk") + " removed."
    print quantity(atomsSurviving, atom) + " survived; " + \
          quantity(atomsRemoved, atom) + " removed."
    print "Which chunks survived: " + summary
    print ""
    
    writeTestcaseTemp("did-round-" + str(chunkSize), True);
   
    return (chunksRemoved > 0)
    
    

# Other reduction algorithms
# (Use these if you're really frustrated with something you know is 1-minimal.)

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

def isPowerOfTwo(n):
    i = 1
    while 1:
        if i == n:
            return True
        if i > n:
            return False
        i *= 2
    

def largestPowerOfTwoSmallerThan(n):
    i = 1
    while 1:
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
