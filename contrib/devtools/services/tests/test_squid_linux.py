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

"""Tests for the linux squid bits."""

import signal

from twisted.trial.unittest import TestCase

from devtools.services import squid


class SquidLinuxTestCase(TestCase):
    """Test the different linux bits."""

    def test_get_auth_process_3(self):
        """Test getting the auth process for squid3."""
        expected = squid.AUTH_PROCESS_PATH % 'squid3'
        self.assertTrue(squid.get_auth_process_path(3).startswith(expected))

    def test_get_auth_process(self):
        """Test getting the auth process."""
        expected = squid.AUTH_PROCESS_PATH % 'squid'
        self.assertTrue(squid.get_auth_process_path(2).startswith(expected))

    def test_format_config_path(self):
        """Test formating a config path."""
        path = '/a/config/path'
        self.assertEqual(path, squid.format_config_path(path))

    def test_kill_squid(self):
        """Test killing squid."""
        called = []

        def fake_kill(pid, kill_signal):
            """Fake os.kill."""
            called.append(('kill', pid, kill_signal))

        self.patch(squid, 'kill', fake_kill)

        squid_pid = 4
        squid.kill_squid(squid_pid)
        self.assertIn(('kill', squid_pid, signal.SIGKILL), called)
