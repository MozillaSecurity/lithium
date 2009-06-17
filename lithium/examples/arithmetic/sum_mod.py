#!/usr/bin/env python

import sys

def interesting(args, tempPrefix):
    mod = int(args[0])
    desired = int(args[1])
    filename = args[2]

    file = open(filename, "r")
    sum = 0
    for line in file:
        line = line.strip()
        if line.isdigit():
            sum += int(line)

    result = sum % mod 
    print str(sum) + " mod " + str(mod) + " is " + str(result)

    return (desired == result)
