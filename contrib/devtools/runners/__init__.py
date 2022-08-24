# Copyright 2009-2012 Canonical Ltd.
# Copyright 2015-2022 Chicharreros (https://launchpad.net/~chicharreros)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the
# OpenSSL library under certain conditions as described in each
# individual source file, and distribute linked combinations
# including the two.
# You must obey the GNU General Public License in all respects
# for all of the code used other than OpenSSL.  If you modify
# file(s) with this exception, you may extend this exception to your
# version of the file(s), but you are not obligated to do so.  If you
# do not wish to do so, delete this exception statement from your
# version.  If you delete this exception statement from all source
# files in the program, then also delete it here.

"""The base test runner object."""

import coverage
import gc
import inspect
import os
import re
import sys
import unittest

from devtools.errors import TestError, UsageError
from devtools.testing.txcheck import TXCheckSuite
from devtools.utils import OptionParser


__all__ = ['BaseTestOptions', 'BaseTestRunner', 'main']


def _is_in_ignored_path(testcase, paths):
    """Return if the testcase is in one of the ignored paths."""
    for ignored_path in paths:
        if testcase.startswith(ignored_path):
            return True
    return False


class BaseTestRunner:
    """The base test runner type. Does not actually run tests."""

    def __init__(self, options=None, *args, **kwargs):
        super(BaseTestRunner, self).__init__(*args, **kwargs)

        # set $HOME to the _trial_temp dir, to avoid breaking user files
        trial_temp_dir = os.environ.get('TRIAL_TEMP_DIR', os.getcwd())
        homedir = os.path.join(trial_temp_dir, options['temp-directory'])
        os.environ['HOME'] = homedir

        # setup $XDG_*_HOME variables and create the directories
        xdg_cache = os.path.join(homedir, 'xdg_cache')
        xdg_config = os.path.join(homedir, 'xdg_config')
        xdg_data = os.path.join(homedir, 'xdg_data')
        os.environ['XDG_CACHE_HOME'] = xdg_cache
        os.environ['XDG_CONFIG_HOME'] = xdg_config
        os.environ['XDG_DATA_HOME'] = xdg_data

        if not os.path.exists(xdg_cache):
            os.makedirs(xdg_cache)
        if not os.path.exists(xdg_config):
            os.makedirs(xdg_config)
        if not os.path.exists(xdg_data):
            os.makedirs(xdg_data)

        # setup the ROOTDIR env var
        os.environ['ROOTDIR'] = os.getcwd()

        # Need an attribute for tempdir so we can use it later
        self.tempdir = homedir
        self.working_dir = os.path.join(self.tempdir, 'trial')

        self.source_files = []
        self.required_services = []

    def _load_unittest(self, relpath):
        """Load unit tests from a Python module with the given 'relpath'."""
        assert relpath.endswith(".py"), (
            "%s does not appear to be a Python module" % relpath
        )
        if not os.path.basename(relpath).startswith('test_'):
            return
        modpath = relpath.replace(os.path.sep, ".")[:-3]
        module = __import__(modpath, None, None, [""])

        # If the module specifies required_services, make sure we get them
        members = [x[1] for x in inspect.getmembers(module, inspect.isclass)]
        for member_type in members:
            if hasattr(member_type, 'required_services'):
                member = member_type()
                for service in member.required_services():
                    if service not in self.required_services:
                        self.required_services.append(service)
                del member
        gc.collect()

        # If the module has a 'suite' or 'test_suite' function, use that
        # to load the tests.
        if hasattr(module, "suite"):
            return module.suite()
        elif hasattr(module, "test_suite"):
            return module.test_suite()
        else:
            return unittest.defaultTestLoader.loadTestsFromModule(module)

    def _collect_tests(
        self, path, test_pattern, ignored_modules, ignored_paths
    ):
        """Return the set of unittests."""
        suite = TXCheckSuite()
        if test_pattern:
            pattern = re.compile('.*%s.*' % test_pattern)
        else:
            pattern = None

        if path:
            try:
                module_suite = self._load_unittest(path)
                if pattern:
                    for inner_suite in module_suite._tests:
                        for test in inner_suite._tests:
                            if pattern.match(test.id()):
                                suite.addTest(test)
                else:
                    suite.addTests(module_suite)
                return suite
            except AssertionError:
                pass
        else:
            raise TestError('Path should be defined.')

        for root, dirs, files in os.walk(path):
            for test in files:
                filepath = os.path.join(root, test)
                if (
                    test.endswith(".py")
                    and test not in ignored_modules
                    and not _is_in_ignored_path(filepath, ignored_paths)
                ):
                    self.source_files.append(filepath)
                    if test.startswith("test_"):
                        module_suite = self._load_unittest(filepath)
                        if pattern:
                            for inner_suite in module_suite._tests:
                                for test in inner_suite._tests:
                                    if pattern.match(test.id()):
                                        suite.addTest(test)
                        else:
                            suite.addTests(module_suite)
        return suite

    def get_suite(self, config):
        """Get the test suite to use."""
        suite = unittest.TestSuite()
        for path in config['tests']:
            suite.addTest(
                self._collect_tests(
                    path,
                    config['test'],
                    config['ignore-modules'],
                    config['ignore-paths'],
                )
            )
        if config['loop']:
            old_suite = suite
            suite = unittest.TestSuite()
            for _ in range(config['loop']):
                suite.addTest(old_suite)

        return suite

    def run_tests(self, suite):
        """Run the test suite."""
        return False


class BaseTestOptions(OptionParser):
    """Base options for our test runner."""

    optFlags = [
        ['coverage', 'c', 'Generate a coverage report for the tests.'],
        ['gui', None, 'Use the GUI mode of some runners.'],
        ['help', 'h', ''],
        ['help-runners', None, 'List information about test runners.'],
    ]

    optParameters = [
        ['test', 't', None, None],
        ['loop', None, 1, None],
        ['ignore-modules', 'i', '', None],
        ['ignore-paths', 'p', '', None],
        ['runner', None, 'txrunner', None],
        ['temp-directory', None, '_trial_temp', None],
    ]

    def __init__(self, *args, **kwargs):
        super(BaseTestOptions, self).__init__(*args, **kwargs)

    def opt_help_runners(self):
        """List the runners which are supported."""
        sys.exit(0)

    def opt_ignore_modules(self, option):
        """Comma-separate list of test modules to ignore,
        e.g: test_gtk.py, test_account.py
        """
        self['ignore-modules'] = list(map(str.strip, option.split(',')))

    def opt_ignore_paths(self, option):
        """Comma-separated list of relative paths to ignore,
        e.g: tests/platform/windows, tests/platform/macosx
        """
        self['ignore-paths'] = list(map(str.strip, option.split(',')))

    def opt_loop(self, option):
        """Loop tests the specified number of times."""
        try:
            self['loop'] = int(option)
        except ValueError:
            raise UsageError('A positive integer value must be specified.')

    def opt_temp_directory(self, option):
        """Path for the working directory for tests (default _trial_temp)."""
        self['temp-directory'] = option

    def opt_test(self, option):
        """Run specific tests, e.g: className.methodName"""
        self['test'] = option

    # We use some camelcase names for trial compatibility here.
    def parseArgs(self, *args):
        """Handle the extra arguments."""
        if isinstance(self.tests, set):
            self['tests'].update(args)
        elif isinstance(self.tests, list):
            self['tests'].extend(args)
        else:
            raise ValueError(args)


def _get_runner_options(runner_name):
    """Return the test runner module, and its options object."""
    module_name = 'devtools.runners.%s' % runner_name
    runner = __import__(module_name, None, None, [''])
    options = None
    if getattr(runner, 'TestOptions', None) is not None:
        options = runner.TestOptions()
    if options is None:
        options = BaseTestOptions()
    return (runner, options)


def main():
    """Do the deed."""
    if len(sys.argv) == 1:
        sys.argv.append('--help')

    try:
        pos = sys.argv.index('--runner')
        runner_name = sys.argv.pop(pos + 1)
        sys.argv.pop(pos)
    except ValueError:
        runner_name = 'txrunner'
    finally:
        runner, options = _get_runner_options(runner_name)
        options.parseOptions()

    test_runner = runner.TestRunner(options=options)
    suite = test_runner.get_suite(options)

    if options['coverage']:
        coverage.erase()
        coverage.start()

    running_services = []

    succeeded = False
    try:
        # Start any required services
        for service_obj in test_runner.required_services:
            service = service_obj()
            service.start_service(tempdir=test_runner.tempdir)
            running_services.append(service)

        succeeded = test_runner.run_tests(suite)
    finally:
        # Stop all the running services
        for service in running_services:
            service.stop_service()

    if options['coverage']:
        coverage.stop()
        coverage.report(
            test_runner.source_files, ignore_errors=True, show_missing=False
        )

    sys.exit(not succeeded)
