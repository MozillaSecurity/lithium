## Using Lithium to reduce bugs in Firefox

Lithium has been used it to make reduced testcases for hundreds of crashes and assertion bugs in Firefox.  Here's how.


### Preparing the testcase

If the testcase is pure JavaScript with no DOM interaction, use the [command-line JavaScript Shell](https://developer.mozilla.org/en-US/docs/Mozilla/Projects/SpiderMonkey/Introduction_to_the_JavaScript_shell) instead of Firefox, as it will be much faster to start the process each time.

If the testcase has to run in Firefox:

1. Make the testcase cause Firefox to exit when finished, using goQuitApplication() in examples/mozilla/quit.js.
1. Tell Lithium what section of the testcase file it is allowed to reduce, by adding comment lines containing "DDBEGIN" and "DDEND" to the file.  This prevents Lithium from needlessly introducing syntax errors or removing the goQuitApplication() call.


### Running Lithium

You'll usually be able to use one of the tests that comes with Lithium.  For these tests, the "..." means (app with args, including testcase).


| Test | Parameters | What it tests |
| --- | --- | --- |
| outputs | timeout, string, app+args | app+args outputs *string* (on stdout or stderr) within *timeout* seconds. |
| hangs | timeout, app+args | app+args does not exit within *timeout* seconds. |
| crashes | timeout, app+args | app+args crashes |
| crashesat (removed) | timeout, signature, app+args | app+args crashes, with *signature* somewhere in the crash log.  Recommend using a function near the top of the stack trace. |

For example, suppose you have a large file called boom.html that triggers an array-bound assertion in debug builds of Firefox.  To make a reduced testcase, you might use something like:

    python -m lithium outputs --timeout=120 "ASSERTION: index out of range" fxdebug/firefox-bin boom.html

Lithium will try to remove as many lines from boom.html as possible while still causing Firefox to print that assertion message.


### Tips

#### All operating systems

- Before testing a given build of Firefox, make sure that build of Firefox is the one you ran most recently.  Otherwise, Firefox will restart in a way that makes it seem to Lithium like Firefox has exited (see [bug 271613](https://bugzilla.mozilla.org/show_bug.cgi?id=271613)).  This kind of restart can also cause a testcase filename to be treated as a hostname ([bug 396003](https://bugzilla.mozilla.org/show_bug.cgi?id=396003)).
- Before testing crashes, [turn off Firefox's Breakpad crash reporter](http://kb.mozillazine.org/Breakpad#Can_I_disable_Crash_Reporter.3F).
- Before testing crashes, [turn off session restore](http://kb.mozillazine.org/Browser.sessionstore.resume_from_crash).
- You might want to edit the test files to hard-code your Firefox path and/or -P profilename.


#### Mac

- Before testing crashes in GUI apps, turn off the OS crash dialog by running CrashReporterPrefs and set it on "Server" mode.  Remember to set it back to "Developer" mode when you're done.
- When using tests based on timed_run.py (crashes.py / hangs.py), give it "firefox-bin", not "firefox".  The "firefox" shell script runs firefox-bin in a way that prevents ntr.py's hang protection from killing firefox-bin.
- Since you'll be using your computer for other things while Lithium reduces the testcase, you'll probably want to work around [bug 507782](https://bugzilla.mozilla.org/show_bug.cgi?id=507782) (pressing the Alt key while Firefox is starting triggers the Safe Mode dialog, even if Firefox doesn't have focus) by commenting out that code in your Firefox tree.


#### Windows

- To turn off the crash dialog, use regedit to change the following keys in [HKEY\_LOCAL\_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AeDebug]:

        "Auto"="1"
        "UserDebuggerHotKey"=dword:00000000
        "Debugger"=""

    Be sure to keep the previous value for Debugger around so you can set it back.
