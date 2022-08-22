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

"""Test the twisted test cases."""

from twisted.internet import defer, protocol
from twisted.spread import pb
from twisted.trial.unittest import TestCase

from devtools.testcases import skipIfOS
from devtools.testcases.txsocketserver import (
    client_protocol_factory,
    server_protocol_factory,
    ServerTestCase,
    TCPPbServerTestCase,
    TidyTCPServer,
    TidyUnixServer,
    TCPServerTestCase,
)


class Adder(pb.Referenceable):
    """A remote adder."""

    def remote_add(self, first, second):
        """Remote adding numbers."""
        return first + second


class Calculator(pb.Root):
    """A calculator ran somewhere on the net."""

    def __init__(self, adder):
        """Create a new instance."""
        self.adder = adder

    def remote_get_adder(self):
        """Get the remote added."""
        return self.adder

    def remote_check_adder(self, other_adder):
        """Check if the are the same."""
        return self.adder == other_adder


class Echoer(pb.Root):
    """An echoer that repeats what we say."""

    def remote_say(self, sentence):
        """Echo what we want to say."""
        return 'Echoer: %s' % sentence


class FakeFactory(object):
    """A fake server/client factory."""

    def __init__(self):
        """Create a new instance."""
        self._disconnecting = False
        self.testserver_on_connection_lost = defer.Deferred()
        self.testserver_on_connection_made = defer.Deferred()


class ProtocolTestCase(TestCase):
    """Test the protocol classes."""

    class_factory = None

    @defer.inlineCallbacks
    def setUp(self):
        """Set the different tests."""
        yield super(ProtocolTestCase, self).setUp()
        self.called = []

        def connection_lost(*args):
            """Fake connection lost method."""
            self.called.append('connectionLost')

        self.patch(pb.Broker, 'connectionLost', connection_lost)

        def connection_made(*args):
            """Fake connection made."""
            self.called.append('connectionMade')

        self.patch(pb.Broker, 'connectionMade', connection_made)

    def test_correct_inheritance(self):
        """Test that the super class is correct."""
        if self.class_factory:
            protocol_cls = self.class_factory(pb.Broker)
            protocol_instance = protocol_cls()
            self.assertIsInstance(protocol_instance, pb.Broker)

    def test_correct_none_inheritance(self):
        """Test the inheritance when the class is none."""
        if self.class_factory:
            protocol_cls = self.class_factory(None)
            protocol_instance = protocol_cls()
            self.assertIsInstance(protocol_instance, protocol.Protocol)

    def _assert_disconnecting(self, disconnecting):
        """Assert the disconnection."""
        if self.class_factory:
            protocol_cls = self.class_factory(pb.Broker)
            prot = protocol_cls()
            prot.factory = FakeFactory()
            prot.factory._disconnecting = disconnecting
            prot.connectionLost()
            self.assertIn(
                'connectionLost',
                self.called,
                'Super connectionLost most be called',
            )
            self.assertEqual(
                disconnecting,
                prot.factory.testserver_on_connection_lost.called,
            )

    def test_connection_lost_disconnecting(self):
        """Test the connectionLost method."""
        self._assert_disconnecting(True)

    def test_connection_lost_not_disconnecting(self):
        """Test the connectionLost method."""
        self._assert_disconnecting(False)

    def test_connection_lost_called(self):
        """Test the connectionLost method."""
        if self.class_factory:
            protocol_cls = self.class_factory(pb.Broker)
            prot = protocol_cls()
            prot.factory = FakeFactory()
            prot.factory._disconnecting = True
            # call the deferred, if the code does not work we will get an
            # exception
            prot.factory.testserver_on_connection_lost.callback(True)
            prot.connectionLost()
            self.assertIn(
                'connectionLost',
                self.called,
                'Super connectionLost must be called',
            )


class TidyServerProtocolTestCase(ProtocolTestCase):
    """Test the generated tidy protocol."""

    @classmethod
    def class_factory(_, *a):
        return server_protocol_factory(*a)


class TidyClientProtocolTestCase(ProtocolTestCase):
    """Test the generated tidy protocol."""

    @classmethod
    def class_factory(_, *a):
        return client_protocol_factory(*a)

    def test_connection_made(self):
        """Test the connectionMade method."""
        # setting the factory here is to work around a pylint bug
        pb.Broker.factory = FakeFactory()
        protocol_cls = self.class_factory(pb.Broker)
        protocol_instance = protocol_cls()
        protocol_instance.connectionMade()
        self.assertIn(
            'connectionMade',
            self.called,
            'Super connectionMade must be called',
        )

    # factory outside init
    def test_connection_made_called(self):
        """Test the connectionMade method."""
        # setting the factory here is to work around a pylint bug
        pb.Broker.factory = FakeFactory()
        protocol_cls = self.class_factory(pb.Broker)

        protocol_instance = protocol_cls()

        # call the deferred, if the code does not work we will get an
        # exception
        protocol_instance.factory.testserver_on_connection_made.callback(True)
        protocol_instance.connectionMade()
        self.assertIn(
            'connectionMade',
            self.called,
            'Super connectionMade must be called',
        )


class TCPPlainTwistedTestCase(ServerTestCase):
    """Test using a server.

    This test class is not testing the server and client per se but testing
    that we can use a PbServerFactory and PbClientFactory in a way that the
    connection will be closed correctly.
    """

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        yield super(TCPPlainTwistedTestCase, self).setUp()
        self.adder = Adder()
        self.calculator = Calculator(self.adder)
        yield self.listen_server(pb.PBServerFactory, self.calculator)
        yield self.connect_client(pb.PBClientFactory)

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyTCPServer()

    @defer.inlineCallbacks
    def test_addition(self):
        """Test adding numbers."""
        first_number = 1
        second_number = 2
        calculator = yield self.client_factory.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        result = yield adder.callRemote('add', first_number, second_number)
        self.assertEqual(first_number + second_number, result)

    @defer.inlineCallbacks
    def test_check_adder(self):
        """Test comparing the adder."""
        calculator = yield self.client_factory.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        check = yield calculator.callRemote('check_adder', adder)
        self.assertTrue(check)


@skipIfOS('win32', 'Unix domain sockets not supported on windows.')
class UnixPlainTwistedTestCase(TCPPlainTwistedTestCase):
    """Test using a server over domain sockets."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyUnixServer()


class TCPNoConnectionTrackingTestCase(TCPServerTestCase):
    """Test using a server.

    This test class is not testing the server and the client perse but testing
    that we can use the PbServerFactory and PbClientFactory in a way that the
    connection will be closed and some of the actions performed in the setup
    and not recorded.
    """

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        yield super(TCPNoConnectionTrackingTestCase, self).setUp()
        self.adder = Adder()
        self.calculator = Calculator(self.adder)
        # connect client and server
        yield self.listen_server(pb.PBServerFactory, self.calculator)
        yield self.connect_client(pb.PBClientFactory)

        self.first_number = 1
        self.second_number = 2
        self.setup_result = None

        # perform some actions before the tests
        calculator = yield self.client_factory.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        self.setup_result = yield adder.callRemote(
            'add', self.first_number, self.second_number
        )

    def test_deferreds(self):
        """Test that the deferreds are not broken."""
        self.assertFalse(self.client_disconnected.called)
        self.assertEqual(None, self.server_disconnected)

    @defer.inlineCallbacks
    def test_addition(self):
        """Test adding numbers."""
        first_number = 1
        second_number = 2
        calculator = yield self.client_factory.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        result = yield adder.callRemote('add', first_number, second_number)
        self.assertEqual(first_number + second_number, result)
        self.assertEqual(self.setup_result, result)

    @defer.inlineCallbacks
    def test_check_adder(self):
        """Test comparing the adder."""
        calculator = yield self.client_factory.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        check = yield calculator.callRemote('check_adder', adder)
        self.assertTrue(check)


@skipIfOS('win32', 'Unix domain sockets not supported on windows.')
class UnixNoConnectionTrackingTestCase(TCPNoConnectionTrackingTestCase):
    """Test using a server over domain sockets."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        # do not point to a dir because the path will be too long
        return TidyUnixServer()


class TCPPlainPbTestCase(TCPPbServerTestCase):
    """Test using a server.

    This test class is not testing the server and client perse but testing
    that we can use a PbServerFactory and PbClientFactory in a way that the
    connection will be closed correctly.
    """

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        yield super(TCPPlainPbTestCase, self).setUp()
        self.adder = Adder()
        self.calculator = Calculator(self.adder)
        yield self.listen_server(self.calculator)
        yield self.connect_client()

    @defer.inlineCallbacks
    def test_addition(self):
        """Test adding numbers."""
        first_number = 1
        second_number = 2
        calculator = yield self.client_factory.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        result = yield adder.callRemote('add', first_number, second_number)
        self.assertEqual(first_number + second_number, result)

    @defer.inlineCallbacks
    def test_check_adder(self):
        """Test comparing the adder."""
        calculator = yield self.client_factory.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        check = yield calculator.callRemote('check_adder', adder)
        self.assertTrue(check)


@skipIfOS('win32', 'Unix domain sockets not supported on windows.')
class UnixPlainPbTestCase(TCPPlainPbTestCase):
    """Test using a server over domain sockets."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyUnixServer()


class TCPMultipleServersTestCase(TestCase):
    """Ensure that several servers can be ran."""

    timeout = 2

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        yield super(TCPMultipleServersTestCase, self).setUp()
        self.first_tcp_server = self.get_server()
        self.second_tcp_server = self.get_server()
        self.adder = Adder()
        self.calculator = Calculator(self.adder)
        self.echoer = Echoer()

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyTCPServer()

    @defer.inlineCallbacks
    def test_single_server(self):
        """Test setting a single server."""
        first_number = 1
        second_number = 2
        yield self.first_tcp_server.listen_server(
            pb.PBServerFactory, self.calculator
        )
        self.addCleanup(self.first_tcp_server.clean_up)
        calculator_c = yield self.first_tcp_server.connect_client(
            pb.PBClientFactory
        )
        calculator = yield calculator_c.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        result = yield adder.callRemote('add', first_number, second_number)
        self.assertEqual(first_number + second_number, result)

    @defer.inlineCallbacks
    def test_multiple_server(self):
        """Test setting multiple server."""
        first_number = 1
        second_number = 2
        # first server
        yield self.first_tcp_server.listen_server(
            pb.PBServerFactory, self.calculator
        )
        self.addCleanup(self.first_tcp_server.clean_up)

        # second server
        yield self.second_tcp_server.listen_server(
            pb.PBServerFactory, self.echoer
        )
        self.addCleanup(self.second_tcp_server.clean_up)

        # connect the diff clients
        calculator_c = yield self.first_tcp_server.connect_client(
            pb.PBClientFactory
        )
        echoer_c = yield self.second_tcp_server.connect_client(
            pb.PBClientFactory
        )

        calculator = yield calculator_c.getRootObject()
        adder = yield calculator.callRemote('get_adder')
        result = yield adder.callRemote('add', first_number, second_number)
        self.assertEqual(first_number + second_number, result)
        echoer = yield echoer_c.getRootObject()
        echo = yield echoer.callRemote('say', 'hello')
        self.assertEqual(self.echoer.remote_say('hello'), echo)

    @defer.inlineCallbacks
    def test_no_single_client(self):
        """Test setting a single server no client."""
        # start server but do not connect a client
        yield self.first_tcp_server.listen_server(
            pb.PBServerFactory, self.calculator
        )
        self.addCleanup(self.first_tcp_server.clean_up)

    @defer.inlineCallbacks
    def test_no_multiple_clients(self):
        """Test setting multiple servers no clients."""
        # first server
        yield self.first_tcp_server.listen_server(
            pb.PBServerFactory, self.calculator
        )
        self.addCleanup(self.first_tcp_server.clean_up)

        # second server
        self.second_tcp_server.listen_server(pb.PBServerFactory, self.echoer)
        self.addCleanup(self.second_tcp_server.clean_up)


@skipIfOS('win32', 'Unix domain sockets not supported on windows.')
class UnixMultipleServersTestCase(TCPMultipleServersTestCase):
    """Ensure that several servers can be ran."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyUnixServer()
