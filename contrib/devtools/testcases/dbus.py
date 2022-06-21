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

"""Base dbus tests cases and test utilities."""

import os
try:
    from urllib.parse import unquote
except ImportError:
    from urllib import unquote

from twisted.internet import defer
# DBusRunner for DBusTestCase using tests
from devtools.services.dbus import DBusRunner
from devtools.testcases import BaseTestCase, skipIf


try:
    import dbus
except ImportError as e:
    dbus = None

try:
    import dbus.service as service
except ImportError:
    service = None

try:
    from dbus.mainloop.glib import DBusGMainLoop
except ImportError:
    DBusGMainLoop = None


class InvalidSessionBus(Exception):
    """Error when we are connected to the wrong session bus in tests."""


class FakeDBusInterface(object):
    """A fake DBusInterface..."""

    def shutdown(self, with_restart=False):
        """...that only knows how to go away"""


@skipIf(dbus is None or service is None or DBusGMainLoop is None,
        "The test requires dbus.")
class DBusTestCase(BaseTestCase):
    """Test the DBus event handling."""

    def required_services(self):
        """Return the list of required services for DBusTestCase."""
        services = super(DBusTestCase, self).required_services()
        services.extend([DBusRunner])
        return services

    @defer.inlineCallbacks
    def setUp(self):
        """Setup the infrastructure fo the test (dbus service)."""
        # dbus modules will be imported by the decorator
        yield super(DBusTestCase, self).setUp()

        # We need to ensure DBUS_SESSION_BUS_ADDRESS is private here
        bus_address = os.environ.get('DBUS_SESSION_BUS_ADDRESS', None)
        if os.path.dirname(unquote(bus_address.split(',')[0].split('=')[1])) \
                != os.path.dirname(os.getcwd()):
            raise InvalidSessionBus('DBUS_SESSION_BUS_ADDRESS is wrong.')

        # Set up the main loop and bus connection
        self.loop = DBusGMainLoop(set_as_default=True)

        # NOTE: The address_or_type value must remain explicitly as
        # str instead of anything from devtools.compat. dbus
        # expects this to be str regardless of version.
        self.bus = dbus.bus.BusConnection(address_or_type=str(bus_address),
                                          mainloop=self.loop)

        # Monkeypatch the dbus.SessionBus/SystemBus methods, to ensure we
        # always point at our own private bus instance.
        self.patch(dbus, 'SessionBus', lambda: self.bus)
        self.patch(dbus, 'SystemBus', lambda: self.bus)

        # Check that we are on the correct bus for real
# Disable this for now, because our tests are extremely broken :(
#        bus_names = self.bus.list_names()
#        if len(bus_names) > 2:
#            raise InvalidSessionBus('Too many bus connections: %s (%r)' %
#                                    (len(bus_names), bus_names))

        # monkeypatch busName.__del__ to avoid errors on gc
        # we take care of releasing the name in shutdown
        service.BusName.__del__ = lambda _: None
        yield self.bus.set_exit_on_disconnect(False)
        self.signal_receivers = set()

    @defer.inlineCallbacks
    def tearDown(self):
        """Cleanup the test."""
        yield self.bus.flush()
        yield self.bus.close()
        yield super(DBusTestCase, self).tearDown()
