#!/usr/bin/env python

# Returns success (0) iff the product of the numbers in the file divides the argument.

# Example: "./product_divides.py 11.txt 35" will return success because 11.txt contains "5" and "7".

import sys

def main():
    filename = sys.argv[1]
    mod = int(sys.argv[2])
    
    file = open(filename, "r")
    prod = 1
    for line in file:
        line = line.strip()
        if line.isdigit():
            prod *= int(line)
                
    if prod % mod == 0:
        print str(prod) + " is divisible by " + str(mod)
        sys.exit(0)
    else:
        print str(prod) + " is not divisible by " + str(mod)
        sys.exit(1)

main()
