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

"""Tests for the network state detection code."""

from collections import defaultdict
from unittest import mock

from twisted.internet.defer import inlineCallbacks

from magicicadaclient.networkstate import (
    linux,
    NetworkFailException,
    NetworkManagerState,
)
from magicicadaclient.networkstate.linux import (
    is_machine_connected,
    NM_DBUS_INTERFACE,
    NM_DBUS_OBJECTPATH,
)
from magicicadaclient.networkstate.networkstates import (
    ONLINE,
    OFFLINE,
    UNKNOWN,
    NM_STATE_ASLEEP,
    NM_STATE_ASLEEP_OLD,
    NM_STATE_CONNECTING,
    NM_STATE_CONNECTING_OLD,
    NM_STATE_CONNECTED_OLD,
    NM_STATE_CONNECTED_LOCAL,
    NM_STATE_CONNECTED_SITE,
    NM_STATE_CONNECTED_GLOBAL,
    NM_STATE_DISCONNECTED,
    NM_STATE_DISCONNECTED_OLD,
    NM_STATE_UNKNOWN,
)
from magicicadaclient.tests import TestCase


class TestException(Exception):
    """An exception to test error conditions."""

    def get_dbus_name(self):
        """A fake dbus name for this exception."""
        return "Test Exception Message"


class FakeNetworkManagerState:

    """Fake Network Manager State."""

    connection_state = None

    def __init__(self, function):
        """Initialize Fake class."""
        self.call_function = function

    def find_online_state(self):
        """Fake find_online_state for linux module."""
        self.call_function(self.connection_state)


class FakeDBusMatch:

    """Fake a DBus match."""

    def __init__(self, name, callback, interface):
        self.name = name
        self.callback = callback
        self.interface = interface
        self.removed = False

    def remove(self):
        """Stop calling the handler function on remove."""
        self.removed = True


class FakeDBusInterface:

    """Fake DBus Interface."""

    def __init__(self):
        self._signals = defaultdict(list)

    def Get(self, *args, **kwargs):
        """Fake Get."""

    def connect_to_signal(self, signal_name, handler_function, dbus_interface):
        """Fake connect_to_signal."""
        match = FakeDBusMatch(signal_name, handler_function, dbus_interface)
        self._signals[signal_name].append(match)
        return match

    def emit_signal(self, signal_name, state):
        """Emit signal for network state change."""
        for match in self._signals[signal_name]:
            match.callback(state)


class FakeSystemBus:

    """Fake SystemBus."""

    objects = {(NM_DBUS_INTERFACE, NM_DBUS_OBJECTPATH, True): object()}

    def get_object(self, interface, object_path, follow_name_owner_changes):
        """Fake get_object."""
        key = (interface, object_path, follow_name_owner_changes)
        return self.objects[key]


class TestConnection(TestCase):

    """Test the state of the connection.

    This TestCase tests over all the connection states possible.

    """

    @inlineCallbacks
    def setUp(self):
        """Setup the mocked dbus object tree."""
        yield super(TestConnection, self).setUp()
        self.patch(linux, "NetworkManagerState", FakeNetworkManagerState)
        self.patch(linux.dbus, 'SystemBus', FakeSystemBus)
        self.nm_interface = FakeDBusInterface()
        self.patch(linux.dbus, 'Interface', lambda *a: self.nm_interface)
        self.network_changes = []

    def _listen_network_changes(self, state):
        """Fake callback function."""
        self.network_changes.append(state)

    def test_network_state_change(self):
        """Test the changes in the network connection."""
        nms = NetworkManagerState(self._listen_network_changes)

        nms.find_online_state()

        self.nm_interface.emit_signal(
            'StateChanged', NM_STATE_CONNECTED_GLOBAL
        )
        self.nm_interface.emit_signal('StateChanged', NM_STATE_DISCONNECTED)
        self.nm_interface.emit_signal(
            'StateChanged', NM_STATE_CONNECTED_GLOBAL
        )

        self.assertEqual(nms.state_signal.name, "StateChanged")
        self.assertEqual(nms.state_signal.callback, nms.state_changed)
        self.assertEqual(
            nms.state_signal.interface, "org.freedesktop.NetworkManager"
        )
        self.assertEqual(
            self.network_changes, [ONLINE, ONLINE, OFFLINE, ONLINE]
        )
        self.assertFalse(nms.state_signal.removed)

    @inlineCallbacks
    def test_is_machine_connected_nm_state_online(self):
        """Callback given ONLINE should mean we are online"""
        self.patch(FakeNetworkManagerState, "connection_state", ONLINE)
        d = yield is_machine_connected()
        self.assertTrue(d)

    @inlineCallbacks
    def test_is_machine_connected_nm_state_offline(self):
        """Callback given OFFLINE should mean we are offline"""
        self.patch(FakeNetworkManagerState, "connection_state", OFFLINE)
        d = yield is_machine_connected()
        self.assertFalse(d)

    @inlineCallbacks
    def test_is_machine_connected_nm_state_unknown(self):
        """Callback given ONLINE should mean we are not online"""
        self.patch(FakeNetworkManagerState, "connection_state", UNKNOWN)
        d = yield is_machine_connected()
        self.assertFalse(d)

    @inlineCallbacks
    def test_is_machine_connected_callback_error(self):
        """Test bad argument to is_machine_connected's internal callback.

        Passing anything other than ONLINE/OFFLINE/UNKNOWN should
        cause an exception.
        """
        self.patch(
            FakeNetworkManagerState,
            "connection_state",
            NM_STATE_CONNECTED_GLOBAL,
        )
        yield self.assertFailure(is_machine_connected(), NetworkFailException)


class NetworkManagerStateTestCase(TestCase):
    """Test NetworkManager state retrieval code."""

    def assert_calls(self, dbusmock):
        dbusmock.SystemBus.assert_called_once()
        sysbusmock = dbusmock.SystemBus.return_value
        proxymock = sysbusmock.get_object.return_value
        ifmock = dbusmock.Interface.return_value

        sysbusmock.get_object.assert_called_once_with(
            'org.freedesktop.NetworkManager',
            '/org/freedesktop/NetworkManager',
            follow_name_owner_changes=True,
        )
        dbusmock.Interface.assert_called_once_with(
            proxymock, 'org.freedesktop.NetworkManager'
        )
        ifmock.connect_to_signal.assert_called_once_with(
            signal_name='StateChanged',
            handler_function=mock.ANY,
            dbus_interface='org.freedesktop.NetworkManager',
        )
        proxymock.state.assert_called_once_with(
            dbus_interface='org.freedesktop.NetworkManager',
            reply_handler=mock.ANY,
            error_handler=mock.ANY,
        )

    def assertOnline(self, state):
        """Check that the state given is ONLINE."""
        self.assertEqual(state, ONLINE)

    def assertOffline(self, state):
        """Check that the state given is OFFLINE."""
        self.assertEqual(state, OFFLINE)

    def assertUnknown(self, state):
        """Check that the state was UNKNOWN."""
        self.assertEqual(state, UNKNOWN)

    def get_nms(self, callback, dbusmock):
        """Get the NetworkManagerState object."""
        nms = NetworkManagerState(callback, dbusmock)
        nms.find_online_state()
        return nms

    def check_nm_error(self, callback, error):
        """Check that the error handling is correct."""
        dbusmock = mock.Mock()
        proxymock = dbusmock.SystemBus.return_value.get_object.return_value
        proxymock.Get.side_effect = error
        self.addCleanup(self.assert_calls, dbusmock)

        nms = self.get_nms(callback, dbusmock)
        nms.got_error(error)

    def check_nm_state(self, callback, state):
        """Check the state handling is correct."""
        dbusmock = mock.Mock()
        self.addCleanup(self.assert_calls, dbusmock)
        nms = self.get_nms(callback, dbusmock)
        nms.got_state(state)

    def check_nm_state_change(self, callback, fmstate, tostate):
        """Check the state change handling is correct."""
        dbusmock = mock.Mock()
        self.addCleanup(self.assert_calls, dbusmock)
        nms = self.get_nms(callback, dbusmock)
        nms.got_state(fmstate)
        nms.state_changed(tostate)

    def test_nm_asleep(self):
        """Asleep status should mean offline."""
        self.check_nm_state(self.assertOffline, NM_STATE_ASLEEP)

    def test_nm_asleep_old(self):
        """Asleep, old status, should mean offline."""
        self.check_nm_state(self.assertOffline, NM_STATE_ASLEEP_OLD)

    def test_nm_unknown(self):
        """Unknown status should be treated the same as OFFLINE."""
        self.check_nm_state(self.assertOffline, NM_STATE_UNKNOWN)

    def test_nm_online_old(self):
        """Check the connected, old status, case."""
        self.check_nm_state(self.assertOnline, NM_STATE_CONNECTED_OLD)

    def test_nm_offline_local(self):
        """Check the connected, local status, case."""
        self.check_nm_state(self.assertOffline, NM_STATE_CONNECTED_LOCAL)

    def test_nm_offline_site(self):
        """Check the connected, site status, case."""
        self.check_nm_state(self.assertOffline, NM_STATE_CONNECTED_SITE)

    def test_nm_online_global(self):
        """Check the connected, global status, case."""
        self.check_nm_state(self.assertOnline, NM_STATE_CONNECTED_GLOBAL)

    def test_nm_offline_old(self):
        """Check the disconnected, old status, case."""
        self.check_nm_state(self.assertOffline, NM_STATE_DISCONNECTED_OLD)

    def test_nm_offline(self):
        """Check the disconnected case."""
        self.check_nm_state(self.assertOffline, NM_STATE_DISCONNECTED)

    def test_nm_connecting_then_online_old(self):
        """Check the waiting for connection, old status, case."""
        self.check_nm_state_change(
            self.assertOnline, NM_STATE_CONNECTING_OLD, NM_STATE_CONNECTED_OLD
        )

    def test_nm_connecting_then_online(self):
        """Check the waiting for connection case."""
        self.check_nm_state_change(
            self.assertOnline, NM_STATE_CONNECTING, NM_STATE_CONNECTED_GLOBAL
        )

    def test_nm_connecting_then_offline_old(self):
        """Check the waiting but fail, old status, case."""
        self.check_nm_state_change(
            self.assertOffline,
            NM_STATE_CONNECTING_OLD,
            NM_STATE_DISCONNECTED_OLD,
        )

    def test_nm_connecting_then_offline(self):
        """Check the waiting but fail case."""
        self.check_nm_state_change(
            self.assertOffline, NM_STATE_CONNECTING, NM_STATE_DISCONNECTED
        )

    def test_nm_check_errors(self):
        """Trying to reach NM fails with some error."""
        self.check_nm_error(self.assertOnline, Exception())

    def test_dbus_problem(self):
        """Check the case when DBus throws some other exception."""
        dbusmock = mock.Mock()
        dbusmock.SystemBus.side_effect = TestException()
        self.get_nms(self.assertOnline, dbusmock)
