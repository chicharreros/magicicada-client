# Copyright 2012-2013 Canonical Ltd.
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

"""Test the twisted webserver."""

from __future__ import unicode_literals

from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.web import client, resource, http

from devtools.testing.txwebserver import HTTPWebServer


SAMPLE_KEY = b"result"
SAMPLE_VALUE = b"sample result"
SAMPLE_RESOURCE = '{{"{0}": "{1}"}}'.format(
    SAMPLE_KEY, SAMPLE_VALUE).encode("utf8")
SIMPLERESOURCE = b"simpleresource"
OTHER_SIMPLERESOURCE = b"othersimpleresource"
THROWERROR = b"throwerror"
UNAUTHORIZED = b"unauthorized"


class SimpleResource(resource.Resource):
    """A simple web resource."""

    def render_GET(self, request):
        """Make a bit of html out of these resource's content."""
        return SAMPLE_RESOURCE


class WebServerTestCase(TestCase):
    """Test the web server that will allow to have connections."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the different tests."""
        yield super(WebServerTestCase, self).setUp()
        # create the root to be used by the webserver
        root = resource.Resource()
        root.putChild(SIMPLERESOURCE, SimpleResource())
        root.putChild(OTHER_SIMPLERESOURCE, SimpleResource())
        root.putChild(THROWERROR, resource.NoResource())

        unauthorized_resource = resource.ErrorPage(http.UNAUTHORIZED,
                                                   "Unauthorized",
                                                   "Unauthorized")
        root.putChild(UNAUTHORIZED, unauthorized_resource)
        self.server = HTTPWebServer(root)
        self.server.start()
        self.uri = "http://127.0.0.1:{port}/".format(
            port=self.server.get_port()).encode("utf8")
        self.addCleanup(self.server.stop)

    @defer.inlineCallbacks
    def test_single_request(self):
        """Test performing a single request to get the data."""
        url = self.uri + SIMPLERESOURCE
        result = yield client.getPage(url)
        self.assertEqual(SAMPLE_RESOURCE, result)

    @defer.inlineCallbacks
    def test_multiple_requests(self):
        """Test performing multiple requests."""
        simple_url = self.uri + SIMPLERESOURCE
        other_simple_url = self.uri + OTHER_SIMPLERESOURCE
        simple_result = yield client.getPage(simple_url)
        other_result = yield client.getPage(other_simple_url)
        self.assertEqual(SAMPLE_RESOURCE, simple_result)
        self.assertEqual(SAMPLE_RESOURCE, other_result)

    def assert_url(self, expected):
        """Assert the url."""
        port = self.server.get_port()
        self.assertEqual(expected.format(port=port), self.server.get_iri())

    def test_get_iri(self):
        """Test getting the iri from the server."""
        expected = "http://127.0.0.1:{port}/"
        self.assert_url(expected)

    def test_get_port(self):
        """Test getting the port."""
        port = self.server.port.getHost().port
        self.assertEqual(port, self.server.get_port())


class MultipleWebServersTestCase(TestCase):
    """Test with multiple webservers running."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        yield super(MultipleWebServersTestCase, self).setUp()
        self.root = resource.Resource()
        self.root.putChild(SIMPLERESOURCE, SimpleResource())
        self.root.putChild(OTHER_SIMPLERESOURCE, SimpleResource())
        self.root.putChild(THROWERROR, resource.NoResource())

        unauthorized_resource = resource.ErrorPage(http.UNAUTHORIZED,
                                                   "Unauthorized",
                                                   "Unauthorized")
        self.root.putChild(UNAUTHORIZED, unauthorized_resource)

    def get_uri(self, server):
        """Return the uri for the server."""
        url = "http://127.0.0.1:{port}/"
        return url.format(port=server.get_port()).encode("utf8")

    @defer.inlineCallbacks
    def test_single_request(self):
        """Test performing a single request to get the data."""
        first_server = HTTPWebServer(self.root)
        first_server.start()
        self.addCleanup(first_server.stop)

        second_server = HTTPWebServer(self.root)
        second_server.start()
        self.addCleanup(second_server.stop)

        for server in [first_server, second_server]:
            url = self.get_uri(server) + SIMPLERESOURCE
            result = yield client.getPage(url)
            self.assertEqual(SAMPLE_RESOURCE, result)

    @defer.inlineCallbacks
    def test_multiple_requests(self):
        """Test performing multiple requests."""
        first_server = HTTPWebServer(self.root)
        first_server.start()
        self.addCleanup(first_server.stop)

        second_server = HTTPWebServer(self.root)
        second_server.start()
        self.addCleanup(second_server.stop)

        for server in [first_server, second_server]:
            simple_url = self.get_uri(server) + SIMPLERESOURCE
            other_simple_url = self.get_uri(server) + OTHER_SIMPLERESOURCE
            simple_result = yield client.getPage(simple_url)
            other_result = yield client.getPage(other_simple_url)
            self.assertEqual(SAMPLE_RESOURCE, simple_result)
            self.assertEqual(SAMPLE_RESOURCE, other_result)
