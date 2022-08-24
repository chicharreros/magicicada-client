# Copyright 2011-2013 Canonical Ltd.
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

"""Test the squid test case."""

import base64

from twisted.application import internet, service
from twisted.internet import defer, reactor
from twisted.web import client, error, http, resource, server
from devtools.testcases import skipIfOS
from devtools.testcases.squid import SquidTestCase

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

SAMPLE_RESOURCE = "<p>Hello World!</p>"
SIMPLERESOURCE = "simpleresource"
THROWERROR = "throwerror"
UNAUTHORIZED = "unauthorized"


class ProxyClientFactory(client.HTTPClientFactory):
    """Factory that supports proxy."""

    def __init__(self, proxy_url, proxy_port, url, headers=None):
        # we set the proxy details before the init because the parent __init__
        # calls setURL
        self.proxy_url = proxy_url
        self.proxy_port = proxy_port
        self.disconnected_d = defer.Deferred()
        client.HTTPClientFactory.__init__(self, url, headers=headers)

    def setURL(self, url):
        self.host = self.proxy_url
        self.port = self.proxy_port
        self.url = url
        self.path = url

    def clientConnectionLost(self, connector, reason, reconnecting=0):
        """Connection lost."""
        self.disconnected_d.callback(self)


class ProxyWebClient(object):
    """Provide useful web methods with proxy."""

    def __init__(
        self, proxy_url=None, proxy_port=None, username=None, password=None
    ):
        """Create a new instance with the proxy settings."""
        self.proxy_url = proxy_url
        self.proxy_port = proxy_port
        self.username = username
        self.password = password
        self.factory = None
        self.connectors = []

    def _connect(self, url, contextFactory):
        """Perform the connection."""
        scheme, _, _, _, _, _ = urlparse(url)
        if scheme == 'https':
            from twisted.internet import ssl

            if contextFactory is None:
                contextFactory = ssl.ClientContextFactory()
            self.connectors.append(
                reactor.connectSSL(
                    self.proxy_url,
                    self.proxy_port,
                    self.factory,
                    contextFactory,
                )
            )
        else:
            self.connectors.append(
                reactor.connectTCP(
                    self.proxy_url, self.proxy_port, self.factory
                )
            )

    def _process_auth_error(self, failure, url, contextFactory):
        """Process an auth failure."""
        failure.trap(error.Error)
        if failure.value.status == str(http.PROXY_AUTH_REQUIRED):
            # we try to get the page using the basic auth
            auth = base64.b64encode('%s:%s' % (self.username, self.password))
            auth_header = 'Basic ' + auth.strip()
            self.factory = ProxyClientFactory(
                self.proxy_url,
                self.proxy_port,
                url,
                headers={'Proxy-Authorization': auth_header},
            )
            self._connect(url, contextFactory)
            return self.factory.deferred
        else:
            return failure

    def get_page(self, url, contextFactory=None, *args, **kwargs):
        """Download a webpage as a string.

        This method relies on the twisted.web.client.getPage but adds and extra
        step. If there is an auth error the method will perform a second try
        so that the username and password are used.
        """
        self.factory = ProxyClientFactory(
            self.proxy_url,
            self.proxy_port,
            url,
            headers={'Connection': 'close'},
        )
        self._connect(url, contextFactory)
        self.factory.deferred.addErrback(
            self._process_auth_error, url, contextFactory
        )
        return self.factory.deferred

    @defer.inlineCallbacks
    def shutdown(self):
        """Clean all connectors."""
        for connector in self.connectors:
            yield connector.disconnect()
        defer.returnValue(True)


class SimpleResource(resource.Resource):
    """A simple web resource."""

    def render_GET(self, request):
        """Make a bit of html out of these resource's
        content."""
        return SAMPLE_RESOURCE


class SaveHTTPChannel(http.HTTPChannel):
    """A save protocol to be used in tests."""

    protocolInstance = None

    def connectionMade(self):
        """Keep track of the given protocol."""
        SaveHTTPChannel.protocolInstance = self
        http.HTTPChannel.connectionMade(self)


class SaveSite(server.Site):
    """A site that let us know when it closed."""

    protocol = SaveHTTPChannel

    def __init__(self, *args, **kwargs):
        """Create a new instance."""
        server.Site.__init__(self, *args, **kwargs)
        # we disable the timeout in the tests, we will deal with it manually.
        self.timeOut = None


class MockWebServer(object):
    """A mock webserver for testing"""

    def __init__(self):
        """Start up this instance."""
        root = resource.Resource()
        root.putChild(SIMPLERESOURCE, SimpleResource())

        root.putChild(THROWERROR, resource.NoResource())

        unauthorized_resource = resource.ErrorPage(
            http.UNAUTHORIZED, "Unauthorized", "Unauthorized"
        )
        root.putChild(UNAUTHORIZED, unauthorized_resource)

        self.site = SaveSite(root)
        application = service.Application('web')
        self.service_collection = service.IServiceCollection(application)
        self.tcpserver = internet.TCPServer(0, self.site)
        self.tcpserver.setServiceParent(self.service_collection)
        self.service_collection.startService()

    def get_url(self):
        """Build the url for this mock server."""
        port_num = self.tcpserver._port.getHost().port
        return "http://127.0.0.1:%d/" % port_num

    @defer.inlineCallbacks
    def stop(self):
        """Shut it down."""
        # make the connection time out so that is works with squid3 when
        # the connection is kept alive.
        if self.site.protocol.protocolInstance:
            self.site.protocol.protocolInstance.timeoutConnection()
        yield self.service_collection.stopService()


class ProxyTestCase(SquidTestCase):
    """A squid test with no auth proxy."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the tests."""
        yield super(ProxyTestCase, self).setUp()
        self.ws = MockWebServer()
        self.proxy_client = None
        self.addCleanup(self.teardown_client_server)
        self.url = self.ws.get_url() + SIMPLERESOURCE

    def teardown_client_server(self):
        """Clean resources."""
        if self.proxy_client is not None:
            self.proxy_client.shutdown()
            return defer.gatherResults(
                [
                    self.ws.stop(),
                    self.proxy_client.shutdown(),
                    self.proxy_client.factory.disconnected_d,
                ]
            )
        else:
            return self.ws.stop()

    def access_noauth_url(self, address, port):
        """Access a url throught the proxy."""
        self.proxy_client = ProxyWebClient(proxy_url=address, proxy_port=port)
        return self.proxy_client.get_page(self.url)

    def access_auth_url(self, address, port, username, password):
        """Access a url throught the proxy."""
        self.proxy_client = ProxyWebClient(
            proxy_url=address,
            proxy_port=port,
            username=username,
            password=password,
        )
        return self.proxy_client.get_page(self.url)

    @defer.inlineCallbacks
    def test_noauth_url_access(self):
        """Test accessing to the url."""
        settings = self.get_nonauth_proxy_settings()
        # if there is an exception we fail.
        data = yield self.access_noauth_url(settings['host'], settings['port'])
        self.assertEqual(SAMPLE_RESOURCE, data)

    @skipIfOS(
        'linux2', 'LP: #1111880 - ncsa_auth crashing for auth proxy tests.'
    )
    @defer.inlineCallbacks
    def test_auth_url_access(self):
        """Test accessing to the url."""
        settings = self.get_auth_proxy_settings()
        # if there is an exception we fail.
        data = yield self.access_auth_url(
            settings['host'],
            settings['port'],
            settings['username'],
            settings['password'],
        )
        self.assertEqual(SAMPLE_RESOURCE, data)

    def test_auth_url_401(self):
        """Test failing accessing the url."""
        settings = self.get_auth_proxy_settings()
        # swap password for username to fail
        d = self.failUnlessFailure(
            self.access_auth_url(
                settings['host'],
                settings['port'],
                settings['password'],
                settings['username'],
            ),
            error.Error,
        )
        return d

    def test_auth_url_407(self):
        """Test failing accessing the url."""
        settings = self.get_auth_proxy_settings()
        d = self.failUnlessFailure(
            self.access_noauth_url(settings['host'], settings['port']),
            error.Error,
        )
        return d
