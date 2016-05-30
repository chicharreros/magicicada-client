# -*- coding: utf-8 -*-
#
# Copyright 2011-2012 Canonical Ltd.
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

"""Tests for the proxy-enabled restful client."""

import logging

try:
    from urllib.parse import urlparse, parse_qs, parse_qsl
except ImportError:
    from urlparse import urlparse, parse_qs, parse_qsl

from twisted.internet import defer
from ubuntuone.devtools.handlers import MementoHandler
from ubuntuone.devtools.testcases import TestCase

from ubuntuone.utils.webclient import restful
from ubuntuone.utils.webclient.common import Response


SAMPLE_SERVICE_IRI = u"http://localhost/"
SAMPLE_NAMESPACE = u"sample_namespace"
SAMPLE_METHOD = u"sample_method"
SAMPLE_OPERATION = SAMPLE_NAMESPACE + u"." + SAMPLE_METHOD
SAMPLE_ARGS = dict(uno=1, dos=u"2", tres=u"ñandú")
SAMPLE_RESPONSE = restful.json.dumps(SAMPLE_ARGS)
SAMPLE_USERNAME = "joeuser@example.com"
SAMPLE_PASSWORD = "clavesecreta"
SAMPLE_AUTH_CREDS = dict(token="1234", etc="456")


class FakeWebClient(object):
    """A fake web client."""

    def __init__(self, **kwargs):
        """Initialize this faker."""
        self.return_value = SAMPLE_RESPONSE
        self.called = []
        self.init_kwargs = kwargs
        self.running = True

    def request(self, iri, *args, **kwargs):
        """Return a deferred that will be fired with a Response object."""
        self.called.append((iri, args, kwargs))
        return defer.succeed(Response(self.return_value))

    def shutdown(self):
        """Stop this fake webclient."""
        self.running = False


class BaseTestCase(TestCase):
    """The base for the Restful Client testcases."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test case."""
        yield super(BaseTestCase, self).setUp()
        self.wc = None
        self.patch(restful.webclient, "webclient_factory",
                   self.webclient_factory)

    def webclient_factory(self, **kwargs):
        """A factory that saves the webclient created."""
        self.wc = FakeWebClient(**kwargs)
        return self.wc


class RestfulClientTestCase(BaseTestCase):
    """Tests for the proxy-enabled Restful Client."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this testcase."""
        yield super(RestfulClientTestCase, self).setUp()
        self.rc = restful.RestfulClient(SAMPLE_SERVICE_IRI)
        self.addCleanup(self.rc.shutdown)

    def test_has_a_webclient(self):
        """The RC has a webclient."""
        self.assertEqual(self.rc.webclient, self.wc)

    def test_shutsdown_the_webclient(self):
        """Calling shutdown on the restful shuts down the webclient too."""
        self.rc.shutdown()
        self.assertFalse(self.rc.webclient.running, "The webclient is stopped")

    @defer.inlineCallbacks
    def test_can_make_calls(self):
        """The RC can make webcalls."""
        yield self.rc.restcall(SAMPLE_OPERATION, **SAMPLE_ARGS)
        self.assertEqual(len(self.wc.called), 1)

    @defer.inlineCallbacks
    def test_restful_namespace_added_to_url(self):
        """The restful namespace is added to the url."""
        yield self.rc.restcall(SAMPLE_OPERATION, **SAMPLE_ARGS)
        iri, _, _ = self.wc.called[0]
        uri = iri.encode("ascii")
        url = urlparse(uri)
        self.assertTrue(url.path.endswith(SAMPLE_NAMESPACE),
                        "The namespace is included in url")

    @defer.inlineCallbacks
    def test_restful_method_added_to_params(self):
        """The restful method is added to the params."""
        yield self.rc.restcall(SAMPLE_OPERATION, **SAMPLE_ARGS)
        _, _, webcall_kwargs = self.wc.called[0]
        wc_params = parse_qs(webcall_kwargs["post_content"])
        self.assertEqual(wc_params["ws.op"][0], SAMPLE_METHOD)

    @defer.inlineCallbacks
    def test_arguments_added_as_json_to_webcall(self):
        """The keyword arguments are used as json in the webcall."""
        yield self.rc.restcall(SAMPLE_OPERATION, **SAMPLE_ARGS)
        _, _, webcall_kwargs = self.wc.called[0]
        params = parse_qsl(webcall_kwargs["post_content"])
        result = {}
        for key, value in params:
            if key == "ws.op":
                continue
            result[key] = restful.json.loads(value)
        self.assertEqual(result, SAMPLE_ARGS)

    @defer.inlineCallbacks
    def test_post_header_sent(self):
        """A header is sent specifying the contents of the post."""
        yield self.rc.restcall(SAMPLE_OPERATION, **SAMPLE_ARGS)
        _, _, webcall_kwargs = self.wc.called[0]
        self.assertEqual(restful.POST_HEADERS,
                         webcall_kwargs["extra_headers"])

    @defer.inlineCallbacks
    def test_post_method_set(self):
        """The method of the webcall is set to POST."""
        yield self.rc.restcall(SAMPLE_OPERATION, **SAMPLE_ARGS)
        _, _, webcall_kwargs = self.wc.called[0]
        self.assertEqual("POST", webcall_kwargs["method"])

    @defer.inlineCallbacks
    def test_return_value_json_parsed(self):
        """The result is json parsed before being returned."""
        result = yield self.rc.restcall(SAMPLE_OPERATION)
        self.assertEqual(result, SAMPLE_ARGS)


class AuthenticationOptionsTestCase(BaseTestCase):
    """Tests for the authentication options."""

    def test_passes_userpass_to_webclient_init(self):
        """The RestfulClient passes the user and pass to the webclient."""
        params = dict(username=SAMPLE_USERNAME, password=SAMPLE_PASSWORD)
        restful.RestfulClient(SAMPLE_SERVICE_IRI, **params)
        expected = dict(params)
        self.assertEqual(self.wc.init_kwargs, expected)

    @defer.inlineCallbacks
    def test_passes_auth_creds_to_request(self):
        """The RestfulClient passes the credentials in each request."""
        kwargs = dict(auth_credentials=SAMPLE_AUTH_CREDS)
        rc = restful.RestfulClient(SAMPLE_SERVICE_IRI, **kwargs)
        yield rc.restcall(SAMPLE_OPERATION, **SAMPLE_ARGS)
        _, _, kwargs = self.wc.called[0]
        self.assertEqual(kwargs["auth_credentials"], SAMPLE_AUTH_CREDS)


class LogginTestCase(BaseTestCase):
    """Ensure that proper debug logging is done."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this testcase."""
        yield super(LogginTestCase, self).setUp()
        self.memento = MementoHandler()
        restful.logger.addHandler(self.memento)
        restful.logger.setLevel(logging.DEBUG)
        self.addCleanup(restful.logger.removeHandler, self.memento)

        self.rc = restful.RestfulClient(SAMPLE_SERVICE_IRI)
        self.addCleanup(self.rc.shutdown)

    @defer.inlineCallbacks
    def test_log_rest_call(self):
        """Check that proper DEBUG is made for every REST call."""
        yield self.rc.restcall(SAMPLE_OPERATION, **SAMPLE_ARGS)

        expected_msgs = (
            SAMPLE_SERVICE_IRI + SAMPLE_NAMESPACE,
        )
        self.assertTrue(self.memento.check_debug(*expected_msgs))

    @defer.inlineCallbacks
    def test_log_json_loads_exception(self):
        """Check that json load errors are properly logged."""
        invalid_json = 'NOTAVALIDJSON'
        self.patch(self.wc, 'return_value', invalid_json)
        yield self.assertFailure(self.rc.restcall(SAMPLE_OPERATION),
                                 ValueError)

        self.memento.debug = True
        expected_msgs = (
            ValueError,
            'Can not load json from REST request response',
            invalid_json
        )
        self.assertTrue(self.memento.check_exception(*expected_msgs))
