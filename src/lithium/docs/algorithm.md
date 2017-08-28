## Analysis of Lithium's algorithm

> By default, Lithium uses a clever algorithm that's efficient at reducing most large testcases.  For a testcase with 2048 lines, it will try removing each chunk of size 1024, permanently removing it if it is still 'interesting'.  It then does the same for each chunk of size 512, then 256, all the way down to chunks of size 1.  It then does as many additional rounds at chunk size 1 as necessary until it completes a round without removing anything, at which point the file is 1-minimal.

> If *n* is the size of the testcase and *m* is the size of the 1-minimal testcase found by Lithium, then Lithium usually performs O(m &sdot; lg(n)) tests with a total test size of O(m &sdot; n).

Lithium's running time behavior depends on whether the 'interestingness test' and testcase together have a property I call monotonicity.

*Monotonicity*: no subsequence of an uninteresting file is ever interesting.  (Equivalently, all relevant supersequences of an interesting file are interesting.)

Note that it's hard to be monotonic without being deterministic.

Note that this condition doesn't require that there is a single, unique 1-minimal testcase.  It only requires that for each 1-minimal testcase, all supersequences are interesting.

| Test/testcase behavior | Running time | Number of tests | Total testcase size |
| --- | --- | --- | --- |
| Monotonic and clustered | Best | O(m + lg(n)) ? | O(m<sup>2</sup> + n) ? |
| Monotonic | Normal | O(m &sdot; lg(n)) | O(m &sdot; n) |
| Non-deterministic or "very non-monotonic" | Worst | O(n<sup>2</sup>) | O(n<sup>3</sup>) |

Most testcases behave roughly monotonically while they're being reduced, as long as the bug is deterministic.  If you see "--" once or twice in Lithium's output, you know there was a minor violation of monotonicity: 


### Normal-case analysis


<!-- "supersequences": it's in the garey & johnson "appendix", therefore it's a word. -->

<!--
An earlier version had a much stronger condition:
XXX make sure the analysis still holds
  3. There is a (single) (minimal) subsequence (with size m) such that:
  3a. If a testcase crashes Firefox, the testcase contains that subsequence.  
  3b. If a testcase contains that subsequence, the testcase crashes Firefox.  
-->

For simplicity, assume *n* is a power of 2.

The key to this analysis is that after every round of removing chunks of size c, there are at most m chunks left.  (So at the beginning at the next round, there are at most 2m chunks.)

Proof: since the testcase behaves monotonically, every attempt to remove a chunk that does not contain any of the elements of the final minimal sequence succeeds.  The final minimal sequence contains *m* elements, so there are at most *m* chunks that survive each round.


#### Tests performed

There are lg(n) chunk sizes, and at each chunk size, there are no more than 2m chunks to try removing.

#### Total lines

XXX get rid of "work"

For simplicity, assume *m* is a power of 2, so that *q* is a power of 2.  Intuitively, *q* is the chunk size beyond which chunks have to start disappearing.

Consider, separately, the amount of work done before and after Lithium acts on chunks of size *q*.  I'll show that each part does O(m &sdot; n) work.

The first round has at most 2 executions, the second at most 4, etc.  For all lg(m) rounds down to chunk size q, there are at most (2 + 4 + 8 + ... + m) < 2m test executions.  Each test execution involves at most n work.  So the total work for the first few rounds is O(n &sdot; m).

For each of the final rounds, with chunk size c < q, the amount of testcase remaining is bounded nicely by c&sdot;m.  At most 2m tests are executed during each round.  So the total work done during each round is (2&sdot;m)&sdot;(c&sdot;m).  Adding it all up, we get (2 + 4 + 8 + ... + q)&sdot;m&sdot;m, which is just less than 2&sdot;h&sdot;m&sdot;m.  Replacing h with m/n, that comes out to 2&sdot;n&sdot;m, which is also O(n &sdot; m).


### Best-case analysis

If all of the important lines are clumped together, I think Lithium ends up pretty much doing a binary search for the interesting area and then O(m) work to verify that the remaining part is 1-minimal. (?)


### Worst-case analysis

In the worst case, Lithium doesn't remove anything until it reaches chunk size 1, then removes only one line from (near the end of) the file each time.

<!--
n is a power of 2
file: 1 ... n
test: other than powers of 2, 

Lithium will go all the way down to chunk size 1 before being able to remove anything.  Then, it will keep chopping one line from the end of the file per round.
-->

Similarly slow behavior can easily show up if the test is non-deterministic, for example if a huge file causes Firefox to crash 2% of the time.  You can offset this kind of non-determinism 


## Comparison to other testcase reduction algorithms

This algorithm has two main differences from [ddmin](https://www.st.cs.uni-saarland.de/papers/tse2002/), the algorithm that inspired Lithium.  First, Lithium doesn't try to "optimistically" reduce to a single chunk like ddmin does, saving a factor of 2 on most testcases.  Second, it doesn't start over from the beginning of the file after removing a chunk, saving a factor of *m* on most testcases.

A simpler approach would be to repeatedly do a binary search for the last (or first) meaningful line of the file and then chop off the rest.  The number of tests would be O(m &sdot; lg n), like Lithium, perhaps with a smaller constant factor.  But the total number of lines would be O(m &sdot; n &sdot; lg n), a factor of lg n worse than Lithium.  When application launch time dominates, I think approach is better by a factor of 2, but when run time dominates, Lithium is better by a factor of lg n (when app run time is linear!)

Interestingly, Lithium doesn't know what *m* is going in, and yet its running time can be expressed in terms of *m*.

It would be interesting to experiment and determine what effect each of these changes has on the running time.  (I wouldn't expect asymptotic changes, just constant-factor changes.)

- Try removing chunks from the end first.
- Use an initial chunk sizes as close as possible to half the size of the file, instead of always using power-of-2 chunk sizes.
- Give users an option to use the "binary search for the last line" algorithm, which might be faster when application startup time dominates.
