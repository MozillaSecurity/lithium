import os
import sys

def importRelativeOrAbsolute(f):
    # maybe there's a way to do this more sanely with the |imp| module...
    if f.endswith(".py"):
        f = f[:-3]
    if f.endswith(".pyc"):
        f = f[:-4]
    p, f = os.path.split(f)
    if p:
        # Add the path part of the given filename to the import path
        sys.path.append(p)
    else:
        # Add working directory to the import path
        sys.path.append(".")
    try:
        module = __import__(f)
    except ImportError, e:
        print "Failed to import: " + f
        print "From: " + __file__
        print str(e)
        raise
    sys.path.pop()
    return module
