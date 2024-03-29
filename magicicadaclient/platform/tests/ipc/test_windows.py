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

"""Tests for the windows ipc."""

from twisted.trial.unittest import TestCase

from magicicadaclient.platform.ipc import windows


class IPCPortTestCase(TestCase):
    """Tests for the ipc port setup."""

    def test_get_sd_pb_port(self):
        """A test for the get_sd_pb_port function."""
        result = windows.get_sd_pb_port()
        self.assertEqual(result, windows.SD_PORT)


class DescriptionFactoryTestCase(TestCase):
    """Tests for the description factory test."""

    def test_init(self):
        """Test that we correctly init the factory."""
        port = 11111
        self.patch(windows, 'get_sd_pb_port', lambda: port)

        factory = windows.DescriptionFactory()
        self.assertEqual(
            factory.server_description_pattern % port, factory.server
        )
        self.assertEqual(
            factory.client_description_pattern % port, factory.client
        )
