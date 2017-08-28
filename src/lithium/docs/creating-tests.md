### Creating your own interestingness tests for Lithium

"Interestingness tests" are Python modules that can be imported by Lithium.

They should export a function called `interesting`.  The first argument to `interesting` will be an array of extra command-line arguments passed to Lithium (if any), and the second will be a suggested prefix for temporary files.  The function should return True if the input is interesting, and False otherwise.  Take care to ensure that input that fails to parse gives False.

Optionally, they can also have a function called "init", which will be called only once with the same array as the first argument to interesting.

Try to design the interestingness test so that the last argument passed will usually be the file the user wants to reduce.  But thanks to the \-\-testcase option, you don't have to do this if it doesn't make sense for your test.


### Ideas

- "The testcase is displayed differently by version X and version Y of Firefox."  This could be an easy way to make reduced testcases for regressions that affect how web pages are displayed.
- Faster test for hangs: automatically reduce the timeout based on how long successful runs take, or assume it's hanging if it outputs nothing for two seconds.
- An "outputs" test that doesn't require restarting Firefox (for reducing non-fatal assertion bugs).
- Interactive, if a bug can only be observed by a human.  (Using Lithium might be faster than manual reduction even in this case!)
