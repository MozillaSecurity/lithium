[![Task Status](https://community-tc.services.mozilla.com/api/github/v1/repository/MozillaSecurity/lithium/master/badge.svg)](https://community-tc.services.mozilla.com/api/github/v1/repository/MozillaSecurity/lithium/master/latest)
[![codecov](https://codecov.io/gh/MozillaSecurity/lithium/branch/master/graph/badge.svg)](https://codecov.io/gh/MozillaSecurity/lithium)
[![Matrix](https://img.shields.io/badge/dynamic/json?color=green&label=chat&query=%24.chunk[%3F(%40.canonical_alias%3D%3D%22%23fuzzing%3Amozilla.org%22)].num_joined_members&suffix=%20users&url=https%3A%2F%2Fmozilla.modular.im%2F_matrix%2Fclient%2Fr0%2FpublicRooms&style=flat&logo=matrix)](https://riot.im/app/#/room/#fuzzing:mozilla.org)
[![PyPI](https://img.shields.io/pypi/v/lithium-reducer)](https://pypi.org/project/lithium-reducer)

## Using Lithium

Lithium is an automated testcase reduction tool developed by [Jesse Ruderman](http://www.squarefree.com/).

Most of what you need to know to use Lithium is in one of these pages:

- [How to use Lithium to reduce Firefox bugs](src/lithium/docs/using-for-firefox.md).  Lithium has been used it to make reduced testcases for hundreds of Firefox crashes and assertions.
- [How to create your own "interestingness tests"](src/lithium/docs/creating-tests.md).  Lithium is flexible enough to reduce files for complicated properties such as "parsed differently by Opera and Firefox".  Just supply a small program that determines when a given file has the property.


### Lithium's algorithm

By default, Lithium uses a clever algorithm that's efficient at reducing most large testcases.  For a testcase with 2048 lines, it will try removing each chunk of size 1024, permanently removing it if it is still 'interesting'.  It then does the same for each chunk of size 512, then 256, all the way down to chunks of size 1.  It then does as many additional rounds at chunk size 1 as necessary until it completes a round without removing anything, at which point the file is 1-minimal (removing any single line from the file makes it 'uninteresting').

If *n* is the size of the testcase and *m* is the size of the 1-minimal testcase found by Lithium, then Lithium usually performs O(m &sdot; lg(n)) tests with a total test size of O(m &sdot; n).  See the [analysis of Lithium's algorithm](src/lithium/docs/algorithm.md) for more information and proofs.

To keep *m* small, make sure Lithium's smallest removals won't introduce fatal syntax errors into the file it is trying to reduce.  For example, don't use --char when trying to reduce a long sequence of JavaScript statements, and don't feed XHTML to Lithium.  (Convert it to HTML first and let Firefox's tag-soup parser sort out the invalidity, or use serializeDOMAsScript.)


### Command line syntax

    pip install lithium-reducer
    python -m lithium [options] interestingness-test.py [arguments for interestingness test]


### Command line options

<dl>

<dt>--testcase=filename</dt>
<dd>Tells Lithium which file to reduce.  By default, it will assume the last argument to the interestingness test is the file to reduce.</dd>

<dt>--char (-c)<dt>
<dd>By default, Lithium treats lines as atomic units.  This is great if each line is a JavaScript statement, but sometimes you want to go further.  Use this option to tell Lithium to treat the file as a sequence of characters instead of a sequence of lines.</dd>

<dt>--strategy=[check-only,minimize,minimize-balanced,replace-properties-by-globals,replace-arguments-by-globals,minimize-around]</dt>
<dd>"minimize" is the default, the algorithm described above. "check-only" tries to run Lithium to determine interestingness, without reduction. For the other strategies, check out <a href="https://github.com/MozillaSecurity/lithium/pull/2">this GitHub PR</a>.</dd>

<dt>--repeat=[always, last, never].</dt>
<dd>By default, Lithium only repeats at the same chunk size if it just finished the last round (e.g. chunk size 1).  You can use --repeat=always to tell it to repeat any chunk size if something was removed during the round, which can be useful for non-deterministic testcases or non-monotonic situations.  You can use --repeat=never to tell it to exit immediately after a single round at the last chunk size, which can save a little time at the risk of leaving a little bit extra in the file.</dd>

<dt>--max=n. default: about half of the file.</dt>
<dt>--min=n. default: 1.</dt>
<dd>What chunk sizes to test.  Must be powers of two.  --max is useful if you're restarting Lithium after it has already gone through a few rounds.  --min is useful if you're reducing HTML and want to do the final by hand.</dd>

<dt>--chunk-size=n</dt>
<dd>Shortcut for "repeat=never, min=n, max=n".  --chunk-size=1 is a quick way to determine whether a file is 1-minimal, for example after making a change that you think might make some lines unnecessary.</dd>

</dl>


### Hints

If you find a non-deterministic bug, don't despair.  Lithium will do fine as long as you make the bug happen at least 70% of the time.  You can repeat the test either within the application, by adding a loop or reload in the testcase (outside of the DDBEGIN/DDEND markers!), or outside of the application, by adding a loop to the "interestingness test" script.


### Requirements

Lithium is written in [Python](https://www.python.org/) and requires Python 3.5+.

### Credits

- [Lithium's testcase reduction algorithm](src/lithium/docs/algorithm.md) is a modified version of the "ddmin" algorithm in Andreas Zeller's paper, [Simplifying and Isolating Failure-Inducing Input](https://www.st.cs.uni-saarland.de/papers/tse2002/).
- The idea of using an external "interestingness test" program came from [Delta](http://delta.tigris.org/), a similar tool that's [used in clever ways by the GCC project](https://gcc.gnu.org/wiki/A_guide_to_testcase_reduction).
- [timed_run](src/lithium/interestingness/timed_run.py), used by many of the "interestingness test" scripts that come with Lithium, is based on [timed_run.py](https://web.archive.org/web/20071107032840/http://bclary.com/log/2007/03/07/timed_run), which was written by [Chris Cooper](http://coop.deadsquid.com/) and [Bob Clary](https://bclary.com/).
- The code was significantly cleaned up and modernized by Jesse Schwartzentruber and Gary Kwong in mid-2017.
