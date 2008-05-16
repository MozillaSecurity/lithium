#!/usr/bin/env python

import sys

def main():
    filename = sys.argv[1]
    mod = int(sys.argv[2])
    desired = int(sys.argv[3])
    
    file = open(filename, "r")
    sum = 0
    for line in file:
        line = line.strip()
        if line.isdigit():
            sum += int(line)
            
    result = sum % mod 
    print str(sum) + " mod " + str(mod) + " is " + str(result)
    
    if desired == result:
        sys.exit(0)
    else:
        sys.exit(1)
    

main()