#!/bin/sh

# exit code: 0 if the first string is found in the console output AND the second string is not found in the console output.
# (you'll also see the matching lines in the console, if any.)

"$2" "$1" &> tmp

grep "$3" tmp && ! grep "$4" tmp
