# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""lithium reducer"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pkg_resources

from .interestingness.utils import rel_or_abs_import
from .strategies import DEFAULT as DEFAULT_STRATEGY
from .testcases import DEFAULT as DEFAULT_TESTCASE
from .util import LithiumError, quantity, summary_header

LOG = logging.getLogger(__name__)


class Lithium:
    """Lithium reduction object."""

    def __init__(self):

        self.strategy = None

        self.condition_script = None
        self.condition_args = None

        self.test_count = 0
        self.test_total = 0

        self.temp_dir = None

        self.testcase = None
        self.last_interesting = None

        self.temp_file_count = 1

    def main(self, argv=None):
        """Main entrypoint (parse args and call `run()`)

        Args:
            argv (list, None): specify command line args

        Return:
            int: 0 for successful reduction
        """
        self.process_args(argv)

        try:
            return self.run()

        except LithiumError:
            summary_header()
            LOG.exception()
            return 1

    def run(self):
        """Reduction Loop

        Returns:
            int: 0 for successful reduction
        """
        if hasattr(self.condition_script, "init"):
            self.condition_script.init(self.condition_args)

        try:
            if self.temp_dir is None:
                self.create_temp_dir()
                LOG.info(
                    "Intermediate files will be stored in %s%s.", self.temp_dir, os.sep
                )

            result = self.strategy.main(
                self.testcase, self.interesting, self.testcase_temp_filename
            )

            LOG.info("  Tests performed: %d", self.test_count)
            LOG.info("  Test total: %s", quantity(self.test_total, self.testcase.atom))

            return result

        finally:
            if hasattr(self.condition_script, "cleanup"):
                self.condition_script.cleanup(self.condition_args)

            # Make sure we exit with an interesting testcase
            if self.last_interesting is not None:
                self.last_interesting.dump()

    def process_args(self, argv=None):
        """Parse command-line args and initialize self.

        Args:
            argv (list, None): specify command line args
        """

        # Try to parse --strategy before anything else
        class _ArgParseTry(argparse.ArgumentParser):
            # pylint: disable=arguments-differ,no-self-argument

            def exit(_, **kwds):
                pass

            def error(_, message):
                pass

        early_parser = _ArgParseTry(add_help=False)
        early_atoms = early_parser.add_mutually_exclusive_group()
        parser = argparse.ArgumentParser(
            description="Lithium, an automated testcase reduction tool",
            epilog="See docs/using-for-firefox.md for more information.",
            usage="%(prog)s [options] condition [condition options] file-to-reduce",
        )
        grp_opt = parser.add_argument_group(description="Lithium options")
        grp_atoms = grp_opt.add_mutually_exclusive_group()

        strategies = {}
        testcase_types = {}
        for entry_point in pkg_resources.iter_entry_points("lithium_strategies"):
            try:
                strategy_cls = entry_point.load()
                assert (
                    strategy_cls.name == entry_point.name
                ), "entry_point name mismatch, check setup.py and %s.name" % (
                    strategy_cls.__name__,
                )
            except Exception as exc:  # pylint: disable=broad-except
                LOG.warning("error loading strategy type %s: %s", entry_point.name, exc)
                continue
            strategies[entry_point.name] = strategy_cls
        assert DEFAULT_STRATEGY in strategies
        for entry_point in pkg_resources.iter_entry_points("lithium_testcases"):
            try:
                testcase_cls = entry_point.load()
                assert testcase_cls.args
                assert testcase_cls.arg_help
            except Exception as exc:  # pylint: disable=broad-except
                LOG.warning("error loading testcase type %s: %s", entry_point.name, exc)
                continue
            testcase_types[testcase_cls.atom] = testcase_cls
            early_atoms.add_argument(
                *testcase_cls.args,
                action="store_const",
                const=testcase_cls.atom,
                dest="atom",
            )
            grp_atoms.add_argument(
                *testcase_cls.args,
                action="store_const",
                const=testcase_cls.atom,
                dest="atom",
                help=testcase_cls.arg_help,
            )
        assert DEFAULT_TESTCASE in testcase_types
        early_parser.set_defaults(atom=DEFAULT_TESTCASE)
        # this is necessary so the first unrecognized option gets collected here
        # otherwise a command line `python -c ...` triggers the --char option
        # in `early_parser`
        early_parser.add_argument(
            "extra_args",
            action="append",
            nargs=argparse.REMAINDER,
        )

        # Try to parse --strategy and testcase_type before anything else
        early_parser.add_argument(
            "--strategy", default=DEFAULT_STRATEGY, choices=strategies.keys()
        )
        args = early_parser.parse_known_args(argv)
        atom = args[0].atom if args else DEFAULT_TESTCASE
        self.strategy = strategies.get(
            args[0].strategy if args else None, strategies[DEFAULT_STRATEGY]
        )()

        grp_opt.add_argument(
            "--testcase", help="testcase file. default: last argument is used."
        )
        grp_opt.add_argument(
            "--tempdir",
            help="specify the directory to use as temporary directory.",
            type=Path,
        )
        grp_opt.add_argument(
            "-v", "--verbose", action="store_true", help="enable verbose debug logging"
        )
        # this has already been parsed above, it's only here for the help message
        grp_opt.add_argument(
            "--strategy",
            default=self.strategy.name,
            choices=strategies.keys(),
            help="reduction strategy to use. default: %s" % DEFAULT_STRATEGY,
        )
        self.strategy.add_args(parser)
        testcase_types[atom].add_arguments(parser)
        grp_ext = parser.add_argument_group(
            description="Condition, condition options and file-to-reduce"
        )
        grp_ext.add_argument(
            "extra_args",
            action="append",
            nargs=argparse.REMAINDER,
            help="condition [condition options] file-to-reduce",
        )

        args = parser.parse_args(argv)
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        self.strategy.process_args(parser, args)

        self.temp_dir = args.tempdir

        extra_args = args.extra_args[0]

        if args.testcase:
            testcase_filename = args.testcase
        elif extra_args:
            # can be overridden by --testcase in processOptions
            testcase_filename = extra_args[-1]
        else:
            parser.error("No testcase specified (use --testcase or last condition arg)")

        LOG.info("Testcase type: %s", atom)
        self.testcase = testcase_types[atom]()
        self.testcase.handle_args(args)
        self.testcase.load(testcase_filename)

        self.condition_script = rel_or_abs_import(extra_args[0])
        self.condition_args = extra_args[1:]

    def testcase_temp_filename(self, filename_stem, use_number=True):
        """Create a temporary filename for the next testcase.

        Args:
            filename_stem (str): Basename for the testcase on disk.
            use_number (bool): Prefix filename with the next number in sequence.

        Returns:
            Path: Filename to use for the next testcase.
        """
        if use_number:
            filename_stem = "%d-%s" % (self.temp_file_count, filename_stem)
            self.temp_file_count += 1
        return self.temp_dir / (filename_stem + self.testcase.extension)

    def create_temp_dir(self):
        """Create and switch to the next available temporary working folder."""
        i = 1
        while True:
            temp_dir = Path("tmp%d" % (i,))
            # To avoid race conditions, we use try/except instead of exists/create
            # Hopefully we don't get any errors other than "File exists" :)
            try:
                temp_dir.mkdir()
            except OSError:
                i += 1
            else:
                self.temp_dir = temp_dir
                break

    # If the file is still interesting after the change, changes "parts" and returns
    # True.
    def interesting(self, testcase_suggestion, write_it=True):
        """Test whether a testcase suggestion is interesting.

        Args:
            testcase_suggestion (Testcase): Testcase to check.
            write_it (bool): Update the original file on disk to the suggestion before
                             running the condition script.

        Returns:
            bool: Whether or not the testcase was interesting.
        """
        if write_it:
            testcase_suggestion.dump()

        self.test_count += 1
        self.test_total += len(testcase_suggestion)

        temp_prefix = str(self.temp_dir / str(self.temp_file_count))

        inter = self.condition_script.interesting(self.condition_args, temp_prefix)

        # Save an extra copy of the file inside the temp directory.
        # This is useful if you're reducing an assertion and encounter a crash:
        # it gives you a way to try to reproduce the crash.
        if self.temp_dir:
            temp_file_tag = "interesting" if inter else "boring"
            testcase_suggestion.dump(self.testcase_temp_filename(temp_file_tag))

        if inter:
            self.testcase = testcase_suggestion
            self.last_interesting = self.testcase

        return inter


def main():
    """Lithium main entrypoint"""
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    sys.exit(Lithium().main())
