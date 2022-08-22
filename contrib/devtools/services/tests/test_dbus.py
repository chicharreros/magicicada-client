# Copyright 2010-2012 Canonical Ltd.
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

"""Tests for the test runner."""

import os
import shutil

from devtools.testcases.dbus import DBusTestCase
from devtools.services.dbus import DBusRunner

try:
    from urllib.parse import unquote
except ImportError:
    from urllib import unquote


class TestWithDBus(DBusTestCase):
    """Test that the DBus runner works correctly."""

    def test_dbus_session_is_running(self):
        """Test that dbus session is the private one we started."""
        bus_address = os.environ.get('DBUS_SESSION_BUS_ADDRESS', None)
        self.assertEqual(
            os.path.dirname(unquote(bus_address.split(',')[0].split('=')[1])),
            os.path.dirname(os.getcwd()),
        )

    def test_config_file_path(self):
        """Test that we loaded the config file from the local tree."""
        expected = os.path.abspath(
            os.path.join(self.tmpdir, 'dbus-session.conf')
        )
        runner = DBusRunner()
        os.makedirs(self.tmpdir)
        runner._generate_config_file(tempdir=self.tmpdir)
        shutil.rmtree(self.tmpdir)
        self.assertEqual(expected, runner.config_file)
