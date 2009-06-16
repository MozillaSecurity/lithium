#!/usr/bin/env python

# Interesting if the product of the numbers in the file divides the argument.

# e.g. lithium product_divides 35 11.txt

import sys

def interesting(args, tempPrefix):
    mod = int(args[0])
    filename = args[1]
    
    file = open(filename, "r")
    prod = 1
    for line in file:
        line = line.strip()
        if line.isdigit():
            prod *= int(line)
                
    if prod % mod == 0:
        print str(prod) + " is divisible by " + str(mod)
        return True
    else:
        print str(prod) + " is not divisible by " + str(mod)
        return False
