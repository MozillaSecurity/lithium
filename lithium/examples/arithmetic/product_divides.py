#!/usr/bin/env python
# coding=utf-8

# Interesting if the product of the numbers in the file divides the argument.

# e.g. lithium product_divides 35 11.txt

import sys


def interesting(args, tempPrefix):
    mod = int(args[0])
    filename = args[1]

    prod = 1
    with open(filename, "r") as input_fp:
        for line in input_fp:
            line = line.strip()
            if line.isdigit():
                prod *= int(line)

    if prod % mod == 0:
        sys.stdout.write("%d is divisible by %d\n" % (prod, mod))
        return True
    else:
        sys.stdout.write("%d is not divisible by %d\n" % (prod, mod))
        return False
