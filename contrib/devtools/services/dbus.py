# Copyright 2009-2012 Canonical Ltd.
# Copyright 2018 Chicharreros (https://launchpad.net/~chicharreros)
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
"""Utilities for finding and running a dbus session bus for testing."""

from __future__ import unicode_literals

import os
import signal
import subprocess

from distutils.spawn import find_executable

try:
    from urllib.parse import quote
except ImportError:
    from urllib import quote

from devtools.services import find_config_file
DBUS_CONFIG_FILE = 'dbus-session.conf.in'


class DBusLaunchError(Exception):
    """Error while launching dbus-daemon"""
    pass


class NotFoundError(Exception):
    """Not found error"""
    pass


class DBusRunner(object):
    """Class for running dbus-daemon with a private session."""

    def __init__(self):
        self.dbus_address = None
        self.dbus_pid = None
        self.running = False
        self.config_file = None

    def _generate_config_file(self, tempdir=None):
        """Find the first appropriate dbus-session.conf to use."""
        # load the config file
        path = find_config_file(DBUS_CONFIG_FILE)
        # replace config settings
        self.config_file = os.path.join(tempdir, 'dbus-session.conf')
        dbus_address = 'unix:tmpdir=%s' % quote(tempdir)
        with open(path) as in_file:
            content = in_file.read()
            with open(self.config_file, 'w') as out_file:
                out_file.write(content.replace('@ADDRESS@', dbus_address))

    def start_service(self, tempdir=None):
        """Start our own session bus daemon for testing."""
        dbus = find_executable("dbus-daemon")
        if not dbus:
            raise NotFoundError("dbus-daemon was not found.")

        self._generate_config_file(tempdir)

        dbus_args = ["--fork",
                     "--config-file=" + self.config_file,
                     "--print-address=1",
                     "--print-pid=2"]
        sp = subprocess.Popen([dbus] + dbus_args,
                              bufsize=4096, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)

        # Call wait here as under the qt4 reactor we get an error about
        # interrupted system call if we don't.
        sp.wait()
        self.dbus_address = b"".join(sp.stdout.readlines()).strip()
        self.dbus_pid = int(b"".join(sp.stderr.readlines()).strip())

        if self.dbus_address != "":
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = \
                self.dbus_address.decode("utf8")
        else:
            os.kill(self.dbus_pid, signal.SIGKILL)
            raise DBusLaunchError("There was a problem launching dbus-daemon.")
        self.running = True

    def stop_service(self):
        """Stop our DBus session bus daemon."""
        try:
            del os.environ["DBUS_SESSION_BUS_ADDRESS"]
        except KeyError:
            pass
        os.kill(self.dbus_pid, signal.SIGKILL)
        self.running = False
        os.unlink(self.config_file)
        self.config_file = None
