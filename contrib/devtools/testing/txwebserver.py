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

"""A tx based web server."""

from __future__ import unicode_literals

from twisted.internet import defer, reactor, ssl
from twisted.protocols.policies import WrappingFactory
from twisted.web import server

from devtools.testcases.txsocketserver import server_protocol_factory


class BaseWebServer(object):
    """Webserver used to perform requests in tests."""

    def __init__(self, root_resource, scheme):
        """Create and start the instance.

        The ssl_settings parameter contains a dictionary with the key and cert
        that will be used to perform ssl connections. The root_resource
        contains the resource with all its childre.
        """
        self.root = root_resource
        self.scheme = scheme
        self.port = None
        # use an http.HTTPFactory that was modified to ensure that we have
        # clean close connections
        self.site = server.Site(self.root, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.wrapper.testserver_on_connection_lost = defer.Deferred()
        self.wrapper.protocol = server_protocol_factory(self.wrapper.protocol)
        self.wrapper._disconnecting = False

    def listen(self, site):
        """Listen a port to allow the tests."""
        raise NotImplementedError('Base abstract class.')

    def get_iri(self):
        """Build the iri for this mock server."""
        return "{scheme}://127.0.0.1:{port}/".format(scheme=self.scheme,
                                                     port=self.get_port())

    def get_port(self):
        """Return the port where we are listening."""
        return self.port.getHost().port

    def start(self):
        """Start the service."""
        self.port = self.listen(self.wrapper)

    def stop(self):
        """Shut it down."""
        if self.port:
            self.wrapper._disconnecting = True
            connected = self.wrapper.protocols.keys()
            if connected:
                for con in connected:
                    con.transport.loseConnection()
            else:
                self.wrapper.testserver_on_connection_lost = \
                    defer.succeed(None)
            d = defer.maybeDeferred(self.port.stopListening)
            return defer.gatherResults(
                [d,
                 self.wrapper.testserver_on_connection_lost])
        return defer.succeed(None)


class HTTPWebServer(BaseWebServer):
    """A Webserver that listens to http connections."""

    def __init__(self, root_resource):
        """Create  a new instance."""
        super(HTTPWebServer, self).__init__(root_resource, 'http')

    def listen(self, site):
        """Listen a port to allow the tests."""
        return reactor.listenTCP(0, site)


class HTTPSWebServer(BaseWebServer):
    """A WebServer that listens to https connections."""

    def __init__(self, root_resource, ssl_settings=None):
        """Create  a new instance."""
        super(HTTPSWebServer, self).__init__(root_resource, 'https')
        self.ssl_settings = ssl_settings

    def listen(self, site):
        """Listen a port to allow the tests."""
        ssl_context = ssl.DefaultOpenSSLContextFactory(
            self.ssl_settings['key'], self.ssl_settings['cert'])

        return reactor.listenSSL(0, site, ssl_context)
