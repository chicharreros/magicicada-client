# -*- coding: utf-8 -*-
#
# Copyright 2011-2013 Canonical Ltd.
# Copyright 2015-2016 Chicharreros (https://launchpad.net/~chicharreros)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT AN WARRANTY; without even the implied warranties of
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

"""Integration tests for the proxy-enabled webclient."""

import logging
import os
import shutil

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from OpenSSL import crypto
from socket import gethostname
from twisted.cred import checkers, portal
from twisted.internet import defer
from twisted.web import guard, http, resource
from ubuntuone.devtools.handlers import MementoHandler
from ubuntuone.devtools.testcases import TestCase, skipIfOS
from ubuntuone.devtools.testcases.squid import SquidTestCase
from ubuntuone.devtools.testing.txwebserver import (
    HTTPWebServer,
    HTTPSWebServer,
)

from ubuntuone.utils import webclient
from ubuntuone.utils.webclient import gsettings, txweb
from ubuntuone.utils.webclient.common import (
    HeaderDict,
    UnauthorizedError,
    WebClientError,
)

ANY_VALUE = object()
SAMPLE_KEY = "result"
SAMPLE_VALUE = "sample result"
SAMPLE_RESOURCE = '{"%s": "%s"}' % (SAMPLE_KEY, SAMPLE_VALUE)
SAMPLE_USERNAME = "peddro"
SAMPLE_PASSWORD = "cantropus"
SAMPLE_CREDENTIALS = dict(username="username", password="password")
SAMPLE_HEADERS = {SAMPLE_KEY: SAMPLE_VALUE}
SAMPLE_POST_PARAMS = {"param1": "value1", "param2": "value2"}
SAMPLE_JPEG_HEADER = '\xff\xd8\xff\xe0\x00\x10JFIF'

SIMPLERESOURCE = "simpleresource"
BYTEZERORESOURCE = "bytezeroresource"
POSTABLERESOURCE = "postableresource"
THROWERROR = "throwerror"
UNAUTHORIZED = "unauthorized"
HEADONLY = "headonly"
VERIFYHEADERS = "verifyheaders"
VERIFYPOSTPARAMS = "verifypostparams"
GUARDED = "guarded"
AUTHRESOURCE = "authresource"

WEBCLIENT_MODULE_NAME = webclient.webclient_module().__name__


def sample_get_credentials():
    """Will return the sample credentials right now."""
    return defer.succeed(SAMPLE_CREDENTIALS)


class SimpleResource(resource.Resource):
    """A simple web resource."""

    def render_GET(self, request):
        """Make a bit of html out of these resource's content."""
        return SAMPLE_RESOURCE


class ByteZeroResource(resource.Resource):
    """A resource that has a nul byte in the middle of it."""

    def render_GET(self, request):
        """Return the content of this resource."""
        return SAMPLE_JPEG_HEADER


class PostableResource(resource.Resource):
    """A resource that only answers to POST requests."""

    def render_POST(self, request):
        """Make a bit of html out of these resource's content."""
        return SAMPLE_RESOURCE


class HeadOnlyResource(resource.Resource):
    """A resource that fails if called with a method other than HEAD."""

    def render_HEAD(self, request):
        """Return a bit of html."""
        return "OK"


class VerifyHeadersResource(resource.Resource):
    """A resource that verifies the headers received."""

    def render_GET(self, request):
        """Make a bit of html out of these resource's content."""
        headers = request.requestHeaders.getRawHeaders(SAMPLE_KEY)
        if headers != [SAMPLE_VALUE]:
            request.setResponseCode(http.BAD_REQUEST)
            return "ERROR: Expected header not present."
        request.setHeader(SAMPLE_KEY, SAMPLE_VALUE)
        return SAMPLE_RESOURCE


class VerifyPostParameters(resource.Resource):
    """A resource that answers to POST requests with some parameters."""

    def fetch_post_args_only(self, request):
        """Fetch only the POST arguments, not the args in the url."""
        request.process = lambda: None
        request.requestReceived(request.method, request.path,
                                request.clientproto)
        return request.args

    def render_POST(self, request):
        """Verify the parameters that we've been called with."""
        post_params = self.fetch_post_args_only(request)
        expected = dict(
            (key, [val]) for key, val in SAMPLE_POST_PARAMS.items())
        if post_params != expected:
            request.setResponseCode(http.BAD_REQUEST)
            return "ERROR: Expected arguments not present, %r != %r" % (
                post_params, expected)
        return SAMPLE_RESOURCE


class SimpleRealm(object):
    """The same simple resource for all users."""

    def requestAvatar(self, avatarId, mind, *interfaces):
        """The avatar for this user."""
        if resource.IResource in interfaces:
            return (resource.IResource, SimpleResource(), lambda: None)
        raise NotImplementedError()


class AuthCheckerResource(resource.Resource):
    """A resource that verifies the request was auth signed."""

    def render_GET(self, request):
        """Make a bit of html out of these resource's content."""
        header = request.requestHeaders.getRawHeaders("Authorization")[0]
        if header.startswith("Auth "):
            return SAMPLE_RESOURCE
        request.setResponseCode(http.BAD_REQUEST)
        return "ERROR: Expected Auth header not present."


def get_root_resource():
    """Get the root resource with all the children."""
    root = resource.Resource()
    root.putChild(SIMPLERESOURCE, SimpleResource())
    root.putChild(BYTEZERORESOURCE, ByteZeroResource())
    root.putChild(POSTABLERESOURCE, PostableResource())

    root.putChild(THROWERROR, resource.NoResource())

    unauthorized_resource = resource.ErrorPage(http.UNAUTHORIZED,
                                               "Unauthorized", "Unauthorized")
    root.putChild(UNAUTHORIZED, unauthorized_resource)
    root.putChild(HEADONLY, HeadOnlyResource())
    root.putChild(VERIFYHEADERS, VerifyHeadersResource())
    root.putChild(VERIFYPOSTPARAMS, VerifyPostParameters())
    root.putChild(AUTHRESOURCE, AuthCheckerResource())

    db = checkers.InMemoryUsernamePasswordDatabaseDontUse()
    db.addUser(SAMPLE_USERNAME, SAMPLE_PASSWORD)
    test_portal = portal.Portal(SimpleRealm(), [db])
    cred_factory = guard.BasicCredentialFactory("example.org")
    guarded_resource = guard.HTTPAuthSessionWrapper(
        test_portal, [cred_factory])
    root.putChild(GUARDED, guarded_resource)
    return root


class HTTPMockWebServer(HTTPWebServer):
    """A mock webserver for the webclient tests."""

    def __init__(self):
        """Create a new instance."""
        root = get_root_resource()
        super(HTTPMockWebServer, self).__init__(root)


class HTTPSMockWebServer(HTTPSWebServer):
    """A mock webserver for the webclient tests."""

    def __init__(self, ssl_settings):
        """Create a new instance."""
        root = get_root_resource()
        super(HTTPSMockWebServer, self).__init__(root, ssl_settings)


class ModuleSelectionTestCase(TestCase):
    """Test the functions to choose the txweb or libsoup backend."""

    def assert_module_name(self, module, expected_name):
        """Check the name of a given module."""
        module_filename = os.path.basename(module.__file__)
        module_name = os.path.splitext(module_filename)[0]
        self.assertEqual(module_name, expected_name)

    def test_webclient_module_libsoup(self):
        """Test the module name for the libsoup case."""
        module = webclient.webclient_module()
        self.assert_module_name(module, "libsoup")


class WebClientTestCase(TestCase):
    """Test for the webclient."""

    timeout = 1
    webclient_factory = webclient.webclient_factory

    @defer.inlineCallbacks
    def setUp(self):
        yield super(WebClientTestCase, self).setUp()
        self.wc = self.webclient_factory()
        self.addCleanup(self.wc.shutdown)
        self.ws = HTTPMockWebServer()
        self.ws.start()
        self.addCleanup(self.ws.stop)
        self.base_iri = self.ws.get_iri()

    @defer.inlineCallbacks
    def test_request_takes_an_iri(self):
        """Passing a non-unicode iri fails."""
        d = self.wc.request(bytes(self.base_iri + SIMPLERESOURCE))
        yield self.assertFailure(d, TypeError)

    @defer.inlineCallbacks
    def test_get_iri(self):
        """Passing in a unicode iri works fine."""
        result = yield self.wc.request(self.base_iri + SIMPLERESOURCE)
        self.assertEqual(SAMPLE_RESOURCE, result.content)

    @defer.inlineCallbacks
    def test_get_iri_error(self):
        """The errback is called when there's some error."""
        yield self.assertFailure(self.wc.request(self.base_iri + THROWERROR),
                                 WebClientError)

    @defer.inlineCallbacks
    def test_zero_byte_in_content(self):
        """Test a reply with a nul byte in the middle of it."""
        result = yield self.wc.request(self.base_iri + BYTEZERORESOURCE)
        self.assertEqual(SAMPLE_JPEG_HEADER, result.content)

    @defer.inlineCallbacks
    def test_post(self):
        """Test a post request."""
        result = yield self.wc.request(self.base_iri + POSTABLERESOURCE,
                                       method="POST")
        self.assertEqual(SAMPLE_RESOURCE, result.content)

    @defer.inlineCallbacks
    def test_post_with_args(self):
        """Test a post request with arguments."""
        args = urlencode(SAMPLE_POST_PARAMS)
        iri = self.base_iri + VERIFYPOSTPARAMS + "?" + args
        headers = {
            "content-type": "application/x-www-form-urlencoded",
        }
        result = yield self.wc.request(
            iri, method="POST", extra_headers=headers, post_content=args)
        self.assertEqual(SAMPLE_RESOURCE, result.content)

    @defer.inlineCallbacks
    def test_unauthorized(self):
        """Detect when a request failed with the UNAUTHORIZED http code."""
        yield self.assertFailure(self.wc.request(self.base_iri + UNAUTHORIZED),
                                 UnauthorizedError)

    @defer.inlineCallbacks
    def test_method_head(self):
        """The HTTP method is used."""
        result = yield self.wc.request(self.base_iri + HEADONLY, method="HEAD")
        self.assertEqual("", result.content)

    @defer.inlineCallbacks
    def test_send_extra_headers(self):
        """The extra_headers are sent to the server."""
        result = yield self.wc.request(self.base_iri + VERIFYHEADERS,
                                       extra_headers=SAMPLE_HEADERS)
        self.assertIn(SAMPLE_KEY, result.headers)
        self.assertEqual(result.headers[SAMPLE_KEY], [SAMPLE_VALUE])

    @defer.inlineCallbacks
    def test_send_basic_auth(self):
        """The basic authentication headers are sent."""
        other_wc = self.webclient_factory(username=SAMPLE_USERNAME,
                                          password=SAMPLE_PASSWORD)
        self.addCleanup(other_wc.shutdown)
        result = yield other_wc.request(self.base_iri + GUARDED)
        self.assertEqual(SAMPLE_RESOURCE, result.content)

    @defer.inlineCallbacks
    def test_send_basic_auth_wrong_credentials(self):
        """Wrong credentials returns a webclient error."""
        other_wc = self.webclient_factory(username=SAMPLE_USERNAME,
                                          password="wrong password!")
        self.addCleanup(other_wc.shutdown)
        yield self.assertFailure(other_wc.request(self.base_iri + GUARDED),
                                 UnauthorizedError)

    @defer.inlineCallbacks
    def test_request_is_auth_signed(self):
        """The request is auth signed."""
        tsc = self.wc.get_timestamp_checker()
        self.patch(tsc, "get_faithful_time", lambda: defer.succeed('1'))
        result = yield self.wc.request(self.base_iri + AUTHRESOURCE,
                                       auth_credentials=SAMPLE_CREDENTIALS)
        self.assertEqual(SAMPLE_RESOURCE, result.content)

    @defer.inlineCallbacks
    def test_auth_signing_uses_timestamp(self):
        """Auth signing uses the timestamp."""
        called = []

        def fake_get_faithful_time():
            """A fake get_timestamp"""
            called.append(True)
            return defer.succeed('1')

        tsc = self.wc.get_timestamp_checker()
        self.patch(tsc, "get_faithful_time", fake_get_faithful_time)
        yield self.wc.request(self.base_iri + AUTHRESOURCE,
                              auth_credentials=SAMPLE_CREDENTIALS)
        self.assertTrue(called, "The timestamp must be retrieved.")

    @defer.inlineCallbacks
    def test_returned_content_are_bytes(self):
        """The returned content are bytes."""
        tsc = self.wc.get_timestamp_checker()
        self.patch(tsc, "get_faithful_time", lambda: defer.succeed('1'))
        result = yield self.wc.request(self.base_iri + AUTHRESOURCE,
                                       auth_credentials=SAMPLE_CREDENTIALS)
        self.assertTrue(isinstance(result.content, bytes),
                        "The type of %r must be bytes" % result.content)

    @defer.inlineCallbacks
    def test_webclienterror_not_string(self):
        """The returned exception contains unicode data."""
        deferred = self.wc.request(self.base_iri + THROWERROR)
        failure = yield self.assertFailure(deferred, WebClientError)
        for error in failure.args:
            self.assertTrue(isinstance(error, basestring))


class FakeSavingReactor(object):
    """A fake reactor that saves connection attempts."""

    def __init__(self):
        """Initialize this fake instance."""
        self.connections = []

    def connectTCP(self, host, port, factory, *args):
        """Fake the connection."""
        self.connections.append((host, port, args))
        factory.response_headers = {}
        factory.deferred = defer.succeed("response content")

    def connectSSL(self, host, port, factory, *args):
        """Fake the connection."""
        self.connections.append((host, port, args))
        factory.response_headers = {}
        factory.deferred = defer.succeed("response content")


class TxWebClientTestCase(WebClientTestCase):
    """Test case for txweb."""

    webclient_factory = txweb.WebClient

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        # delay import, otherwise a default reactor gets installed
        from twisted.web import client
        self.factory = client.HTTPClientFactory
        # set the factory to be used
        # Hook the server's buildProtocol to make the protocol instance
        # accessible to tests and ensure that the reactor is clean!
        build_protocol = self.factory.buildProtocol
        self.serverProtocol = None

        def remember_protocol_instance(my_self, addr):
            """Remember the protocol used in the test."""
            protocol = build_protocol(my_self, addr)
            self.serverProtocol = protocol
            on_connection_lost = defer.Deferred()
            connection_lost = protocol.connectionLost

            def defer_connection_lost(protocol, *a):
                """Lost connection."""
                if not on_connection_lost.called:
                    on_connection_lost.callback(None)
                connection_lost(protocol, *a)

            self.patch(protocol, 'connectionLost', defer_connection_lost)

            def cleanup():
                """Clean the connection."""
                if self.serverProtocol.transport is not None:
                    self.serverProtocol.transport.loseConnection()
                return on_connection_lost

            self.addCleanup(cleanup)
            return protocol

        self.factory.buildProtocol = remember_protocol_instance
        self.addCleanup(self.set_build_protocol, build_protocol)
        txweb.WebClient.client_factory = self.factory

        yield super(TxWebClientTestCase, self).setUp()

    def set_build_protocol(self, method):
        """Set the method back."""
        self.factory.buildProtocol = method


class TxWebClientReactorReplaceableTestCase(TestCase):
    """In the txweb client the reactor is replaceable."""

    timeout = 3
    FAKE_HOST = u"fake"
    FAKE_IRI_TEMPLATE = u"%%s://%s/fake_page" % FAKE_HOST

    @defer.inlineCallbacks
    def _test_replaceable_reactor(self, iri):
        """The reactor can be replaced with the tunnel client."""
        fake_reactor = FakeSavingReactor()
        wc = txweb.WebClient(fake_reactor)
        _response = yield wc.request(iri)
        assert(_response)
        host, _port, _args = fake_reactor.connections[0]
        self.assertEqual(host, self.FAKE_HOST)

    def test_replaceable_reactor_http(self):
        """Test the replaceable reactor with an http iri."""
        return self._test_replaceable_reactor(self.FAKE_IRI_TEMPLATE % "http")

    def test_replaceable_reactor_https(self):
        """Test the replaceable reactor with an https iri."""
        return self._test_replaceable_reactor(self.FAKE_IRI_TEMPLATE % "https")


class TimestampCheckerTestCase(TestCase):
    """Tests for the timestampchecker classmethod."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this testcase."""
        yield super(TimestampCheckerTestCase, self).setUp()
        self.wc = webclient.webclient_factory()
        self.patch(self.wc.__class__, "timestamp_checker", None)

    def test_timestamp_checker_has_the_same_class_as_the_creator(self):
        """The TimestampChecker has the same class."""
        tsc = self.wc.get_timestamp_checker()
        self.assertEqual(tsc.webclient_class, self.wc.__class__)

    def test_timestamp_checker_is_the_same_for_all_webclients(self):
        """The TimestampChecker is the same for all webclients."""
        tsc1 = self.wc.get_timestamp_checker()
        wc2 = webclient.webclient_factory()
        tsc2 = wc2.get_timestamp_checker()
        self.assertIs(tsc1, tsc2)


class BasicProxyTestCase(SquidTestCase):
    """Test that the proxy works at all."""

    timeout = 3

    @defer.inlineCallbacks
    def setUp(self):
        yield super(BasicProxyTestCase, self).setUp()
        self.ws = HTTPMockWebServer()
        self.ws.start()
        self.addCleanup(self.ws.stop)
        self.base_iri = self.ws.get_iri()
        self.wc = webclient.webclient_factory()
        self.addCleanup(self.wc.shutdown)

    def assert_header_contains(self, headers, expected):
        """One of the headers matching key must contain a given value."""
        self.assertTrue(any(expected in value for value in headers))

    @defer.inlineCallbacks
    def test_anonymous_proxy_is_used(self):
        """The anonymous proxy is used by the webclient."""
        settings = self.get_nonauth_proxy_settings()
        self.wc.force_use_proxy(settings)
        result = yield self.wc.request(self.base_iri + SIMPLERESOURCE)
        self.assert_header_contains(result.headers["Via"], "squid")

    @skipIfOS('linux2',
              'LP: #1111880 - ncsa_auth crashing for auth proxy tests.')
    @defer.inlineCallbacks
    def test_authenticated_proxy_is_used(self):
        """The authenticated proxy is used by the webclient."""
        settings = self.get_auth_proxy_settings()
        self.wc.force_use_proxy(settings)
        result = yield self.wc.request(self.base_iri + SIMPLERESOURCE)
        self.assert_header_contains(result.headers["Via"], "squid")

    if WEBCLIENT_MODULE_NAME.endswith(".txweb"):
        reason = "txweb does not support proxies."
        test_anonymous_proxy_is_used.skip = reason
        test_authenticated_proxy_is_used.kip = reason


class HeaderDictTestCase(TestCase):
    """Tests for the case insensitive header dictionary."""

    def test_constructor_handles_keys(self):
        """The constructor handles case-insensitive keys."""
        hd = HeaderDict({"ClAvE": "value"})
        self.assertIn("clave", hd)

    def test_can_set_get_items(self):
        """The item is set/getted."""
        hd = HeaderDict()
        hd["key"] = "value"
        hd["KEY"] = "value2"
        self.assertEqual(hd["key"], "value2")

    def test_can_test_presence(self):
        """The presence of an item is found."""
        hd = HeaderDict()
        self.assertNotIn("cLaVe", hd)
        hd["CLAVE"] = "value1"
        self.assertIn("cLaVe", hd)
        del(hd["cLAVe"])
        self.assertNotIn("cLaVe", hd)


class FakeKeyring(object):
    """A fake keyring."""

    def __init__(self, creds):
        """A fake keyring."""
        self.creds = creds

    def __call__(self):
        """Fake instance callable."""
        return self

    def get_credentials(self, domain):
        """A fake get_credentials."""
        if isinstance(self.creds, Exception):
            return defer.fail(self.creds)
        return defer.succeed(self.creds)


class BaseSSLTestCase(SquidTestCase):
    """Base test that allows to use ssl connections."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        yield super(BaseSSLTestCase, self).setUp()
        self.cert_dir = os.path.join(self.tmpdir, 'cert')
        self.cert_details = dict(organization='Canonical',
                                 common_name=gethostname(),
                                 locality_name='London',
                                 unit='Ubuntu One',
                                 country_name='UK',
                                 state_name='London',)
        self.ssl_settings = self._generate_self_signed_certificate(
            self.cert_dir,
            self.cert_details)
        self.addCleanup(self._clean_ssl_certificate_files)

        self.ws = HTTPSMockWebServer(self.ssl_settings)
        self.ws.start()
        self.addCleanup(self.ws.stop)
        self.base_iri = self.ws.get_iri()

    def _clean_ssl_certificate_files(self):
        """Remove the certificate files."""
        if os.path.exists(self.cert_dir):
            shutil.rmtree(self.cert_dir)

    def _generate_self_signed_certificate(self, cert_dir, cert_details):
        """Generate the required SSL certificates."""
        if not os.path.exists(cert_dir):
            os.makedirs(cert_dir)
        cert_path = os.path.join(cert_dir, 'cert.crt')
        key_path = os.path.join(cert_dir, 'cert.key')

        if os.path.exists(cert_path):
            os.unlink(cert_path)
        if os.path.exists(key_path):
            os.unlink(key_path)

        # create a key pair
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, 1024)

        # create a self-signed cert
        cert = crypto.X509()
        cert.get_subject().C = cert_details['country_name']
        cert.get_subject().ST = cert_details['state_name']
        cert.get_subject().L = cert_details['locality_name']
        cert.get_subject().O = cert_details['organization']
        cert.get_subject().OU = cert_details['unit']
        cert.get_subject().CN = cert_details['common_name']
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)
        cert.sign(key, 'sha1')

        with open(cert_path, 'wt') as fd:
            fd.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

        with open(key_path, 'wt') as fd:
            fd.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))

        return dict(key=key_path, cert=cert_path)


class CorrectProxyTestCase(BaseSSLTestCase):
    """Test the interaction with a SSL enabled proxy."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the tests."""
        yield super(CorrectProxyTestCase, self).setUp()

        # fake the gsettings to have diff settings for https and http
        http_settings = self.get_auth_proxy_settings()
        https_settings = self.get_nonauth_proxy_settings()

        proxy_settings = dict(http=http_settings, https=https_settings)
        self.patch(gsettings, "get_proxy_settings", lambda: proxy_settings)

        self.wc = webclient.webclient_factory()
        self.addCleanup(self.wc.shutdown)

        self.called = []

    def assert_header_contains(self, headers, expected):
        """One of the headers matching key must contain a given value."""
        self.assertTrue(any(expected in value for value in headers))

    @defer.inlineCallbacks
    def test_https_request(self):
        """Test using the correct proxy for the ssl request.

        In order to assert that the correct proxy is used we expect not to call
        the auth dialog since we set the https proxy not to use the auth proxy
        and to fail because we are reaching a https page with bad self-signed
        certs.
        """
        # we fail due to the fake ssl cert
        yield self.failUnlessFailure(self.wc.request(
                                     self.base_iri + SIMPLERESOURCE),
                                     WebClientError)
        # https requests do not use the auth proxy therefore called should be
        # empty. This asserts that we are using the correct settings for the
        # request.
        self.assertEqual([], self.called)

    @defer.inlineCallbacks
    def test_http_request(self):
        """Test using the correct proxy for the plain request.

        This tests does the opposite to the https tests. We did set the auth
        proxy for the http request therefore we expect the proxy dialog to be
        used and not to get an error since we are not visiting a https with bad
        self-signed certs.
        """
        # we do not fail since we are not going to the https page
        result = yield self.wc.request(self.base_iri + SIMPLERESOURCE)
        self.assert_header_contains(result.headers["Via"], "squid")

    if WEBCLIENT_MODULE_NAME.endswith(".txweb"):
        reason = 'Multiple proxy settings is not supported.'
        test_https_request.skip = reason
        test_http_request.skip = reason

    if WEBCLIENT_MODULE_NAME.endswith(".libsoup"):
        reason = 'Hard to test since we need to fully mock gsettings.'
        test_https_request.skip = reason
        test_http_request.skip = reason


class SSLTestCase(BaseSSLTestCase):
    """Test error handling when dealing with ssl."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the diff tests."""
        yield super(SSLTestCase, self).setUp()

        self.memento = MementoHandler()
        self.memento.setLevel(logging.DEBUG)
        logger = webclient.webclient_module().logger
        logger.addHandler(self.memento)
        self.addCleanup(logger.removeHandler, self.memento)

        self.wc = webclient.webclient_factory()
        self.addCleanup(self.wc.shutdown)

        self.called = []

    def test_ssl_fail(self):
        """Test showing the dialog and rejecting."""
        self.failUnlessFailure(self.wc.request(
                self.base_iri + SIMPLERESOURCE), WebClientError)
        self.assertNotEqual(None, self.memento.check_error('SSL errors'))

    if (WEBCLIENT_MODULE_NAME.endswith(".txweb") or
            WEBCLIENT_MODULE_NAME.endswith(".libsoup")):
        reason = 'SSL support has not yet been implemented.'
        test_ssl_fail.skip = reason
