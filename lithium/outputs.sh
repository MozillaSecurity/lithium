#!/bin/sh

# exit code: 0 if the given string is found in the console output, 1 if not. 
# (you'll also see the matching lines in the console, if any.)

"$2" "$1" &> tmp

grep "$3" tmp
