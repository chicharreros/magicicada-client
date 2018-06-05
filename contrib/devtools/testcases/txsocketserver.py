# -*- coding: utf-8 -*-
# Copyright 2012 Canonical Ltd.
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

"""Base test case for twisted servers."""

import os
import shutil
import tempfile

from twisted.internet import defer, endpoints, protocol
from twisted.spread import pb

from devtools.testcases import BaseTestCase

# no init method + twisted common warnings
# pylint: disable=W0232, C0103, E1101


def server_protocol_factory(cls):
    """Factory to create tidy protocols."""

    if cls is None:
        cls = protocol.Protocol

    class ServerTidyProtocol(cls):
        """A tidy protocol."""

        def connectionLost(self, *args):
            """Lost the connection."""
            cls.connectionLost(self, *args)
            # lets tell everyone
            # pylint: disable=W0212
            if (self.factory._disconnecting and
                    self.factory.testserver_on_connection_lost is not None and
                    not self.factory.testserver_on_connection_lost.called):
                self.factory.testserver_on_connection_lost.callback(self)
            # pylint: enable=W0212

    return ServerTidyProtocol


def server_factory_factory(cls):
    """Factory that creates special types of factories for tests."""

    if cls is None:
        cls = protocol.ServerFactory

    class TidyServerFactory(cls):
        """A tidy factory."""

        testserver_on_connection_lost = None

        def buildProtocol(self, addr):
            prot = cls.buildProtocol(self, addr)
            self.testserver_on_connection_lost = defer.Deferred()
            return prot

    return TidyServerFactory


def client_protocol_factory(cls):
    """Factory to create tidy protocols."""

    if cls is None:
        cls = protocol.Protocol

    class ClientTidyProtocol(cls):
        """A tidy protocol."""

        def connectionLost(self, *a):
            """Connection list."""
            cls.connectionLost(self, *a)
            # pylint: disable=W0212
            if (self.factory._disconnecting and
                    self.factory.testserver_on_connection_lost is not None and
                    not self.factory.testserver_on_connection_lost.called):
                self.factory.testserver_on_connection_lost.callback(self)
            # pylint: enable=W0212

    return ClientTidyProtocol


class TidySocketServer(object):
    """Ensure that twisted servers are correctly managed in tests.

    Closing a twisted server is a complicated matter. In order to do so you
    have to ensure that three different deferreds are fired:

        1. The server must stop listening.
        2. The client connection must disconnect.
        3. The server connection must disconnect.

    This class allows to create a server and a client that will ensure that
    the reactor is left clean by following the pattern described at
    http://mumak.net/stuff/twisted-disconnect.html
    """
    def __init__(self):
        """Create a new instance."""
        self.listener = None
        self.server_factory = None

        self.connector = None
        self.client_factory = None

    def get_server_endpoint(self):
        """Return the server endpoint description."""
        raise NotImplementedError('To be implemented by child classes.')

    def get_client_endpoint(self):
        """Return the client endpoint description."""
        raise NotImplementedError('To be implemented by child classes.')

    @defer.inlineCallbacks
    def listen_server(self, server_class, *args, **kwargs):
        """Start a server in a random port."""
        from twisted.internet import reactor
        tidy_class = server_factory_factory(server_class)
        self.server_factory = tidy_class(*args, **kwargs)
        self.server_factory._disconnecting = False
        self.server_factory.protocol = server_protocol_factory(
            self.server_factory.protocol)
        endpoint = endpoints.serverFromString(reactor,
                                              self.get_server_endpoint())
        self.listener = yield endpoint.listen(self.server_factory)
        defer.returnValue(self.server_factory)

    @defer.inlineCallbacks
    def connect_client(self, client_class, *args, **kwargs):
        """Conect a client to a given server."""
        from twisted.internet import reactor

        if self.server_factory is None:
            raise ValueError('Server Factory was not provided.')
        if self.listener is None:
            raise ValueError('%s has not started listening.',
                             self.server_factory)

        self.client_factory = client_class(*args, **kwargs)
        self.client_factory._disconnecting = False
        self.client_factory.protocol = client_protocol_factory(
            self.client_factory.protocol)
        self.client_factory.testserver_on_connection_lost = defer.Deferred()
        endpoint = endpoints.clientFromString(reactor,
                                              self.get_client_endpoint())
        self.connector = yield endpoint.connect(self.client_factory)
        defer.returnValue(self.client_factory)

    def clean_up(self):
        """Action to be performed for clean up."""
        if self.server_factory is None or self.listener is None:
            # nothing to clean
            return defer.succeed(None)

        if self.listener and self.connector:
            # clean client and server
            self.server_factory._disconnecting = True
            self.client_factory._disconnecting = True
            d = defer.maybeDeferred(self.listener.stopListening)
            self.connector.transport.loseConnection()
            if self.server_factory.testserver_on_connection_lost:
                return defer.gatherResults(
                    [d,
                     self.client_factory.testserver_on_connection_lost,
                     self.server_factory.testserver_on_connection_lost])
            else:
                return defer.gatherResults(
                    [d,
                     self.client_factory.testserver_on_connection_lost])
        if self.listener:
            # just clean the server since there is no client
            # pylint: disable=W0201
            self.server_factory._disconnecting = True
            return defer.maybeDeferred(self.listener.stopListening)
            # pylint: enable=W0201


class TidyTCPServer(TidySocketServer):
    """A tidy tcp domain sockets server."""

    client_endpoint_pattern = 'tcp:host=127.0.0.1:port=%s'
    server_endpoint_pattern = 'tcp:0:interface=127.0.0.1'

    def get_server_endpoint(self):
        """Return the server endpoint description."""
        return self.server_endpoint_pattern

    def get_client_endpoint(self):
        """Return the client endpoint description."""
        if self.server_factory is None:
            raise ValueError('Server Factory was not provided.')
        if self.listener is None:
            raise ValueError('%s has not started listening.',
                             self.server_factory)
        return self.client_endpoint_pattern % self.listener.getHost().port


class TidyUnixServer(TidySocketServer):
    """A tidy unix domain sockets server."""

    client_endpoint_pattern = 'unix:path=%s'
    server_endpoint_pattern = 'unix:%s'

    def __init__(self):
        """Create a new instance."""
        super(TidyUnixServer, self).__init__()
        self.temp_dir = tempfile.mkdtemp()
        self.path = os.path.join(self.temp_dir, 'tidy_unix_server')

    def get_server_endpoint(self):
        """Return the server endpoint description."""
        return self.server_endpoint_pattern % self.path

    def get_client_endpoint(self):
        """Return the client endpoint description."""
        return self.client_endpoint_pattern % self.path

    def clean_up(self):
        """Action to be performed for clean up."""
        result = super(TidyUnixServer, self).clean_up()
        # remove the dir once we are disconnected
        result.addCallback(lambda _: shutil.rmtree(self.temp_dir))
        return result


class ServerTestCase(BaseTestCase):
    """Base test case for tidy servers."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        yield super(ServerTestCase, self).setUp()

        try:
            self.server_runner = self.get_server()
        except NotImplementedError:
            self.server_runner = None

        self.server_factory = None
        self.client_factory = None
        self.server_disconnected = None
        self.client_connected = None
        self.client_disconnected = None
        self.listener = None
        self.connector = None
        self.addCleanup(self.tear_down_server_client)

    def get_server(self):
        """Return the server to be used to run the tests."""
        raise NotImplementedError('To be implemented by child classes.')

    @defer.inlineCallbacks
    def listen_server(self, server_class, *args, **kwargs):
        """Listen a server.

        The method takes the server class and the arguments that should be
        passed to the server constructor.
        """
        self.server_factory = yield self.server_runner.listen_server(
            server_class, *args, **kwargs)
        self.server_disconnected = \
            self.server_factory.testserver_on_connection_lost
        self.listener = self.server_runner.listener

    @defer.inlineCallbacks
    def connect_client(self, client_class, *args, **kwargs):
        """Connect the client.

        The method takes the client factory  class and the arguments that
        should be passed to the client constructor.
        """
        self.client_factory = yield self.server_runner.connect_client(
            client_class, *args, **kwargs)
        self.client_disconnected = \
            self.client_factory.testserver_on_connection_lost
        self.connector = self.server_runner.connector

    def tear_down_server_client(self):
        """Clean the server and client."""
        if self.server_runner:
            return self.server_runner.clean_up()


class TCPServerTestCase(ServerTestCase):
    """Test that uses a single twisted server."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyTCPServer()


class UnixServerTestCase(ServerTestCase):
    """Test that uses a single twisted server."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyUnixServer()


class PbServerTestCase(ServerTestCase):
    """Test a pb server."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        raise NotImplementedError('To be implemented by child classes.')

    @defer.inlineCallbacks
    def listen_server(self, *args, **kwargs):
        """Listen a pb server."""
        yield super(PbServerTestCase, self).listen_server(pb.PBServerFactory,
                                                          *args, **kwargs)

    @defer.inlineCallbacks
    def connect_client(self, *args, **kwargs):
        """Connect a pb client."""
        yield super(PbServerTestCase, self).connect_client(pb.PBClientFactory,
                                                           *args, **kwargs)


class TCPPbServerTestCase(PbServerTestCase):
    """Test a pb server over TCP."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyTCPServer()


class UnixPbServerTestCase(PbServerTestCase):
    """Test a pb server over Unix domain sockets."""

    def get_server(self):
        """Return the server to be used to run the tests."""
        return TidyUnixServer()
