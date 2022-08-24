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

"""The twisted test runner and options."""

import sys

from twisted.internet import defer
from twisted.python import failure
from twisted.scripts import trial
from twisted.trial.runner import TrialRunner

from devtools.errors import TestError
from devtools.runners import BaseTestOptions, BaseTestRunner

__all__ = ['TestRunner', 'TestOptions']


def _initialDebugSetup():
    # Taken from Twisted's src/twisted/scripts/trial.py
    failure.startDebugMode()
    defer.setDebugging(True)


class TestRunner(BaseTestRunner, TrialRunner):
    """The twisted test runner implementation."""

    def __init__(self, options=None):
        # Handle running trial in debug or dry-run mode
        self.config = options

        try:
            reactor_name = 'devtools.reactors.%s' % (self.config['reactor'],)
            reactor = __import__(reactor_name, None, None, [''])
        except ImportError:
            raise TestError('The specified reactor is not supported.')
        else:
            try:
                reactor.install(options=self.config)
            except ImportError:
                raise TestError(
                    'The Python package providing the requested reactor is '
                    'not installed. You can find it here: %s'
                    % reactor.REACTOR_URL
                )

        mode = None
        debugger = None
        if self.config['debug']:
            _initialDebugSetup()
            mode = TrialRunner.DEBUG
            import pdb

            debugger = pdb
        if self.config['dry-run']:
            mode = TrialRunner.DRY_RUN

        # Hook up to the parent test runner
        super(TestRunner, self).__init__(
            options=options,
            reporterFactory=self.config['reporter'],
            mode=mode,
            debugger=debugger,
            profile=self.config['profile'],
            logfile=self.config['logfile'],
            tracebackFormat=self.config['tbformat'],
            realTimeErrors=self.config['rterrors'],
            uncleanWarnings=self.config['unclean-warnings'],
            forceGarbageCollection=self.config['force-gc'],
        )
        # Named for trial compatibility.
        self.workingDirectory = self.working_dir

    def run_tests(self, suite):
        """Run the twisted test suite."""
        if self.config['until-failure']:
            result = self.runUntilFailure(suite)
        else:
            result = self.run(suite)
        return result.wasSuccessful()


def _get_default_reactor():
    """Return the platform-dependent default reactor to use."""
    default_reactor = 'gi'
    if sys.platform in ['darwin', 'win32']:
        default_reactor = 'twisted'
    return default_reactor


class TestOptions(trial.Options, BaseTestOptions):
    """Class for twisted options handling."""

    optFlags = [["help-reactors", None]]

    optParameters = [["reactor", "r", _get_default_reactor()]]

    def __init__(self, *args, **kwargs):
        super(TestOptions, self).__init__(*args, **kwargs)
        self['rterrors'] = True

    def opt_coverage(self, option):
        """Handle special flags."""
        self['coverage'] = True

    opt_c = opt_coverage

    def opt_help_reactors(self):
        """Help on available reactors for use with tests"""
        synopsis = ''
        print(synopsis)
        print('Need to get list of reactors and print them here.\n')
        sys.exit(0)

    def opt_reactor(self, option):
        """Which reactor to use (see --help-reactors for a list
        of possibilities)
        """
        self['reactor'] = option

    opt_r = opt_reactor
