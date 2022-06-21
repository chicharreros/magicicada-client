# Copyright 2012 Canonical Ltd.
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

"""Test the utils module."""

from __future__ import print_function, unicode_literals

from twisted.internet.defer import inlineCallbacks
from devtools.errors import UsageError
from devtools.testcases import BaseTestCase
from devtools.utils import OptionParser


class FakeOptions(OptionParser):
    """Fake options class for testing."""

    optFlags = [['foo', 'f', 'Save the manatees.'],
                ['bar', None, 'Beyond all recognition.'],
                ]

    optParameters = [['stuff', 's', 'things'],
                     ]

    def __init__(self, *args, **kwargs):
        super(FakeOptions, self).__init__(*args, **kwargs)

    def opt_foo(self):
        """Handle the foo flag."""
        pass

    def opt_stuff(self, option):
        """Handle the stuff option."""
        self['stuff'] = option


class OptionParserTestCase(BaseTestCase):
    """Test the OptionParser class."""

    @inlineCallbacks
    def setUp(self, *args, **kwargs):
        yield super(OptionParserTestCase, self).setUp(*args, **kwargs)
        self.options = FakeOptions()

    def test_get_flags_long_arg(self):
        """Test that getting a flag works properly."""
        args = ['--foo', 'pathname']
        self.options.parseOptions(options=args)
        self.assertTrue(self.options['foo'])

    def test_get_flags_short_arg(self):
        """Test that using the short version of a flag works."""
        args = ['-f', 'pathname']
        self.options.parseOptions(options=args)
        self.assertTrue(self.options['foo'])

    def test_get_params_combined_arg(self):
        """Test that getting a parameter works properly."""
        expected = 'baz'
        args = ['--stuff=' + expected, 'pathname']
        self.options.parseOptions(options=args)
        self.assertEqual(expected, self.options['stuff'])

    def test_get_params_missing_arg(self):
        """Test that passing no parameter argument fails correctly."""
        args = ['--stuff']
        self.assertRaises(UsageError, self.options.parseOptions, options=args)

    def test_get_params_short_arg(self):
        """Test that using the short version of a parameter works."""
        expected = 'baz'
        args = ['-s', expected, 'pathname']
        self.options.parseOptions(options=args)
        self.assertEqual(expected, self.options['stuff'])

    def test_get_params_split_arg(self):
        """Test that passing a parameter argument separately works."""
        expected = 'baz'
        args = ['--stuff', expected, 'pathname']
        self.options.parseOptions(options=args)
        self.assertEqual(expected, self.options['stuff'])

    def test_unknown_option(self):
        """Test that passing an unknown option fails."""
        args = ['--unknown', 'pathname']
        self.assertRaises(UsageError, self.options.parseOptions, options=args)
