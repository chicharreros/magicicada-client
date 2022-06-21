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

"""Tests for the windows squid bits."""

import win32api
import win32con

from twisted.trial.unittest import TestCase

from devtools.services import squid


class SquidWindowsTestCase(TestCase):
    """"Test the different windows bits."""

    def test_get_auth_process(self):
        """Test getting the auth process for squid3."""
        called = []

        self.patch(squid, 'find_executable', lambda _: None)

        def fake_format(path):
            """Fake format of a config path."""
            called.append(('format', path))
            return path

        self.patch(squid, 'format_config_path', fake_format)
        self.assertTrue(squid.get_auth_process_path(3).startswith(
            squid.AUTH_PROCESS_PATH))
        self.assertIn(('format',
                       squid.AUTH_PROCESS_PATH + squid.AUTH_PROCESS_NAME),
                      called)

    def test_get_auth_process_path(self):
        """Test getting the auth process."""
        called = []

        exec_path = '/path/to/exec'
        self.patch(squid, 'find_executable', lambda _: exec_path)

        def fake_format(path):
            """Fake format of a config path."""
            called.append(('format', path))
            return path

        self.patch(squid, 'format_config_path', fake_format)
        self.assertEqual(exec_path, squid.get_auth_process_path(3))
        self.assertIn(('format', exec_path), called)

    def test_format_config_path(self):
        """Test formating a config path."""
        path = '\\a\\config\\path'
        expected = path.replace('\\', '\\\\')
        self.assertEqual(expected, squid.format_config_path(path))

    def test_kill_squid(self):
        """Test killing squid."""
        called = []

        def fake_open_process(access, inherit, pid):
            """A fake open process."""
            called.append(('OpenProcess', access, inherit, pid))
            return pid

        self.patch(win32api, 'OpenProcess', fake_open_process)

        def fake_terminate(handle, exit_code):
            """Fake terminate the process."""
            called.append(('TerminateProcess', handle, exit_code))

        self.patch(win32api, 'TerminateProcess', fake_terminate)

        def fake_close_handle(handle):
            """Fale closing a handle."""
            called.append(('CloseHandle', handle))

        self.patch(win32api, 'CloseHandle', fake_close_handle)
        squid_pid = 4
        squid.kill_squid(squid_pid)
        self.assertIn(('OpenProcess', win32con.PROCESS_TERMINATE, 0,
                      squid_pid), called)
        self.assertIn(('TerminateProcess', squid_pid, 0), called)
        self.assertIn(('CloseHandle', squid_pid), called)
