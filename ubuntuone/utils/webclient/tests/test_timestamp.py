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

"""Tests for the timestamp sync classes."""

from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.web import resource

from ubuntuone.devtools.testing.txwebserver import HTTPWebServer

from ubuntuone.utils.webclient import timestamp, webclient_module


class FakedError(Exception):
    """Stub to replace Request.error."""


class RootResource(resource.Resource):
    """A root resource that logs the number of calls."""

    isLeaf = True

    def __init__(self, *args, **kwargs):
        """Initialize this fake instance."""
        resource.Resource.__init__(self, *args, **kwargs)
        self.count = 0
        self.request_headers = []

    def render_HEAD(self, request):
        """Increase the counter on each render."""
        self.request_headers.append(request.requestHeaders)
        self.count += 1
        return ""


class MockWebServer(HTTPWebServer):
    """A mock webserver for testing."""

    def __init__(self):
        """Create a new server."""
        super(MockWebServer, self).__init__(RootResource())


class TimestampCheckerTestCase(TestCase):
    """Tests for the timestamp checker."""

    timeout = 5

    @defer.inlineCallbacks
    def setUp(self):
        yield super(TimestampCheckerTestCase, self).setUp()
        self.ws = MockWebServer()
        self.ws.start()
        self.addCleanup(self.ws.stop)
        self.webclient_class = webclient_module().WebClient
        self.patch(timestamp.TimestampChecker, "SERVER_IRI", self.ws.get_iri())

    @defer.inlineCallbacks
    def test_returned_value_is_int(self):
        """The returned value is an integer."""
        checker = timestamp.TimestampChecker(self.webclient_class)
        result = yield checker.get_faithful_time()
        self.assertEqual(type(result), int)

    @defer.inlineCallbacks
    def test_first_call_does_head(self):
        """The first call gets the clock from our web."""
        checker = timestamp.TimestampChecker(self.webclient_class)
        yield checker.get_faithful_time()
        self.assertEqual(self.ws.root.count, 1)

    @defer.inlineCallbacks
    def test_second_call_is_cached(self):
        """For the second call, the time is cached."""
        checker = timestamp.TimestampChecker(self.webclient_class)
        yield checker.get_faithful_time()
        yield checker.get_faithful_time()
        self.assertEqual(self.ws.root.count, 1)

    @defer.inlineCallbacks
    def test_after_timeout_cache_expires(self):
        """After some time, the cache expires."""
        fake_timestamp = 1
        self.patch(timestamp.time, "time", lambda: fake_timestamp)
        checker = timestamp.TimestampChecker(self.webclient_class)
        yield checker.get_faithful_time()
        fake_timestamp += timestamp.TimestampChecker.CHECKING_INTERVAL
        yield checker.get_faithful_time()
        self.assertEqual(self.ws.root.count, 2)

    @defer.inlineCallbacks
    def test_server_error_means_skew_not_updated(self):
        """When server can't be reached, the skew is not updated."""
        fake_timestamp = 1
        self.patch(timestamp.time, "time", lambda: fake_timestamp)
        checker = timestamp.TimestampChecker(self.webclient_class)
        self.patch(
            checker, "get_server_time", lambda _: defer.fail(FakedError()))
        yield checker.get_faithful_time()
        self.assertEqual(checker.skew, 0)
        self.assertEqual(
            checker.next_check,
            fake_timestamp + timestamp.TimestampChecker.ERROR_INTERVAL)

    @defer.inlineCallbacks
    def test_server_date_sends_nocache_headers(self):
        """Getting the server date sends the no-cache headers."""
        checker = timestamp.TimestampChecker(self.webclient_class)
        yield checker.get_server_date_header(self.ws.get_iri())
        self.assertEqual(len(self.ws.root.request_headers), 1)
        headers = self.ws.root.request_headers[0]
        result = headers.getRawHeaders("Cache-Control")
        self.assertEqual(result, ["no-cache"])
