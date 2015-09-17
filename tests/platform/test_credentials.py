# -*- coding: utf-8 -*-
#
# Authors: Manuel de la Pena <manuel@canonical.com>
#          Alejandro J. Cura <alecu@canonical.com>
#
# Copyright 2011-2012 Canonical Ltd.
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
"""Platform independent tests for the credentials management."""

import platform
import urllib
import urlparse

from collections import defaultdict
from functools import wraps

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from contrib.testing.testcase import FAKED_CREDENTIALS
from ubuntuone import clientdefs
from ubuntuone.platform.credentials import (
    BASE_PING_URL,
    CredentialsError,
    CredentialsManagementTool,
    DESCRIPTION,
    HELP_TEXT_KEY,
    NO_OP,
    PING_URL,
    PING_URL_KEY,
    platform_data,
    POLICY_URL,
    POLICY_URL_KEY,
    TC_URL,
    TC_URL_KEY,
    UI_EXECUTABLE_KEY,
    UI_EXECUTABLE_QT,
    UI_PARAMS,
)


class FakedSignal(object):
    """A faked signal."""

    def __init__(self, name, callback):
        self.name = name
        self.callback = callback
        self.removed = False
        self.remove = lambda: setattr(self, 'removed', True)


class FakedProxy(object):
    """Fake a CredentialsManagement proxy."""

    error_dict = None
    error_handler = None

    def __init__(self, *args, **kwargs):
        self._credentials = None
        self._args = None
        self._kwargs = None
        self._signals = []
        self._receivers = defaultdict(list)
        self._called = defaultdict(list)

    def connect_to_signal(self, signal_name, callback):
        """Keep track of connected signals."""
        self._receivers[signal_name].append(callback)
        result = FakedSignal(signal_name, callback)
        self._signals.append(result)
        return result

    def maybe_emit_error(f):
        """Decorator to fake a CredentialsError signal."""

        @wraps(f)
        def inner(self, *args, **kwargs):
            """Fake a CredentialsError signal."""
            if self.error_dict is None and self.error_handler is None:
                f(self, *args, **kwargs)

            reply_handler = kwargs.pop('reply_handler', NO_OP)
            error_handler = kwargs.pop('error_handler', NO_OP)
            if self.error_handler is not None:
                error_handler(self.error_handler)
            else:
                reply_handler()

            if self.error_dict is not None:
                self.CredentialsError(self.error_dict)

        return inner

    def record_call(f):
        """Decorator to record calls to 'f'."""

        @wraps(f)
        def inner(self, *a, **kw):
            """Record the call to 'f' and call it."""
            self._called[f.__name__].append((a, kw))
            return f(self, *a, **kw)

        return inner

    def emit_signal(f):
        """Decorator to emit a signal."""

        @wraps(f)
        def inner(self, *args, **kwargs):
            """Emit the signal."""
            for cb in self._receivers[f.__name__]:
                cb(*args, **kwargs)

        return inner

    @emit_signal
    def AuthorizationDenied(self):
        """Signal thrown when the user denies the authorization."""

    @emit_signal
    def CredentialsFound(self, credentials):
        """Signal thrown when the credentials are found."""

    @emit_signal
    def CredentialsNotFound(self):
        """Signal thrown when the credentials are not found."""

    @emit_signal
    def CredentialsCleared(self):
        """Signal thrown when the credentials were cleared."""

    @emit_signal
    def CredentialsStored(self):
        """Signal thrown when the credentials were stored."""

    @emit_signal
    def CredentialsError(self, error_dict):
        """Signal thrown when there is a problem getting the credentials."""

    @record_call
    @maybe_emit_error
    def find_credentials(self, reply_handler=NO_OP, error_handler=NO_OP):
        """Look for the credentials for an application."""
        if self._credentials is not None:
            self.CredentialsFound(self._credentials)
        else:
            self.CredentialsNotFound()

    @record_call
    @maybe_emit_error
    def clear_credentials(self, reply_handler=NO_OP, error_handler=NO_OP):
        """Clear the credentials for an application."""
        self._credentials = None
        self.CredentialsCleared()

    @record_call
    @maybe_emit_error
    def store_credentials(self, credentials,
                          reply_handler=NO_OP, error_handler=NO_OP):
        """Store the token for an application."""
        self._credentials = credentials
        self.CredentialsStored()

    @record_call
    @maybe_emit_error
    def register(self, dict_arg,
                 reply_handler=NO_OP, error_handler=NO_OP):
        """Get credentials if found else prompt GUI to register."""
        creds = self._credentials
        if creds is not None and len(creds) > 0:
            self.CredentialsFound(creds)
        elif creds == {}:
            # fake an AuthorizationDenied
            self.AuthorizationDenied()
        elif creds is None:
            # fake the adding of the credentials
            self._credentials = FAKED_CREDENTIALS
            self.CredentialsFound(FAKED_CREDENTIALS)

    @record_call
    @maybe_emit_error
    def login(self, dict_arg,
              reply_handler=NO_OP, error_handler=NO_OP):
        """Get credentials if found else prompt GUI to login."""
        self.register(dict_arg, reply_handler, error_handler)

    @record_call
    @maybe_emit_error
    def login_email_password(self, dict_arg,
                             reply_handler=NO_OP, error_handler=NO_OP):
        """Fake login_email_password."""
        self.register(dict_arg, reply_handler, error_handler)


class FakedPlatformSource(object):
    """Faked the platform source."""

    def get_creds_proxy(self):
        """Return a new faked proxy every time, so we can test proxy caching."""
        return FakedProxy()


class CredentialsManagementToolTestCase(TestCase):
    """Test case for the object that manages Magicicada credentials."""

    timeout = 3
    error_dict = None
    error_handler = None

    @defer.inlineCallbacks
    def setUp(self):
        yield super(CredentialsManagementToolTestCase, self).setUp()
        self.cred_tool = CredentialsManagementTool()
        self.patch(self.cred_tool, 'get_platform_source', FakedPlatformSource)
        self.proxy = yield self.cred_tool.get_creds_proxy()
        self.proxy.error_dict = self.error_dict
        self.proxy.error_handler = self.error_handler

        self.window_id_arg = {'window_id': '803'}
        self.email_password_arg = {'email': 'foo@bar.com', 'password': 'yadda'}

    @defer.inlineCallbacks
    def test_proxy_is_reused(self):
        """The inner proxy is re-used."""
        proxy1 = yield self.cred_tool.get_creds_proxy()
        proxy2 = yield self.cred_tool.get_creds_proxy()
        self.assertTrue(proxy1 is proxy2)

    def test_ui_params(self):
        """The UI_PARAMS dict is correct."""
        expected = {
            HELP_TEXT_KEY: DESCRIPTION,
            PING_URL_KEY: PING_URL,
            POLICY_URL_KEY: POLICY_URL,
            TC_URL_KEY: TC_URL,
            UI_EXECUTABLE_KEY: UI_EXECUTABLE_QT,
        }
        self.assertEqual(expected, UI_PARAMS)


class ArgsTestCase(CredentialsManagementToolTestCase):
    """Test case to check that proper arguments are passed to SSO backend."""

    @defer.inlineCallbacks
    def assert_method_called(self, method_name, *args, **kwargs):
        """Test that 'method_name' was called once with 'args' and 'kwargs."""
        self.assertIn(method_name, self.proxy._called)

        calls = self.proxy._called[method_name]
        msg = '%s must be called only once (got %s instead).'
        self.assertEqual(len(calls), 1, msg % (method_name, len(calls)))

        actual_args, actual_kwargs = calls[0]
        self.assertEqual(args, actual_args)

        reply_handler = actual_kwargs.pop('reply_handler', None)
        self.assertFalse(reply_handler is None, 'Must provide a reply_handler')
        d = defer.Deferred()
        reply_handler(deferred=d)
        yield d
        self.assertTrue(d.called)

        error_handler = actual_kwargs.pop('error_handler', None)
        self.assertFalse(error_handler is None, 'Must provide a error_handler')
        d = defer.Deferred()
        error_handler(error='foo', deferred=d)
        e = yield self.assertFailure(d, CredentialsError)
        self.assertEqual(e.message, 'foo')

        self.assertEqual(kwargs, actual_kwargs)

    @defer.inlineCallbacks
    def test_find_credentials(self):
        """The find_credentials method calls proper method."""
        yield self.cred_tool.find_credentials()

        self.assert_method_called('find_credentials')

    @defer.inlineCallbacks
    def test_clear_credentials(self):
        """The clear_credentials method calls proper method."""
        yield self.cred_tool.clear_credentials()

        self.assert_method_called('clear_credentials')

    @defer.inlineCallbacks
    def test_store_credentials(self):
        """The store_credentials method calls proper method."""
        yield self.cred_tool.store_credentials(FAKED_CREDENTIALS)

        self.assert_method_called('store_credentials', FAKED_CREDENTIALS)

    @defer.inlineCallbacks
    def test_register(self):
        """The register method calls proper method."""
        yield self.cred_tool.register(**self.window_id_arg)

        self.assert_method_called('register', self.window_id_arg)

    @defer.inlineCallbacks
    def test_login(self):
        """The login method calls proper method."""
        yield self.cred_tool.login(**self.window_id_arg)

        self.assert_method_called('login', self.window_id_arg)

    @defer.inlineCallbacks
    def test_login_email_password(self):
        """The login method calls proper method."""
        yield self.cred_tool.login_email_password(**self.email_password_arg)

        self.assert_method_called('login_email_password',
                                  self.email_password_arg)


class NoErrorWithCredsTestCase(CredentialsManagementToolTestCase):
    """Test case when there was no error, and credentials are present."""

    token = {'test': 'me'}

    @defer.inlineCallbacks
    def do_test(self, method, expected=None, **kwargs):
        """Perform the test itself."""
        if self.token is not None:
            self.proxy.store_credentials(self.token)
        else:
            yield self.proxy.clear_credentials()
        actual = yield method(**kwargs)
        self.assertEqual(expected, actual)

    @defer.inlineCallbacks
    def test_find_credentials(self):
        """The find_credentials method calls proper method."""
        yield self.do_test(self.cred_tool.find_credentials, self.token)

    @defer.inlineCallbacks
    def test_clear_credentials(self):
        """The clear_credentials method calls proper method."""
        yield self.do_test(self.cred_tool.clear_credentials, None)

    @defer.inlineCallbacks
    def test_store_credentials(self):
        """The store_credentials method calls proper method."""
        yield self.do_test(self.cred_tool.store_credentials, None,
                           token=FAKED_CREDENTIALS)

    @defer.inlineCallbacks
    def test_register(self):
        """The register method calls proper method."""
        yield self.do_test(self.cred_tool.register, self.token,
                           **self.window_id_arg)

    @defer.inlineCallbacks
    def test_login(self):
        """The login method calls proper method."""
        yield self.do_test(self.cred_tool.login, self.token,
                           **self.window_id_arg)

    @defer.inlineCallbacks
    def test_login_email_password(self):
        """The login_email_password method calls proper method."""
        yield self.do_test(self.cred_tool.login_email_password, self.token,
                           **self.email_password_arg)


class NoErrorNoCredsTestCase(NoErrorWithCredsTestCase):
    """Test case when there was no error, and credentials are not present."""

    token = None

    @defer.inlineCallbacks
    def test_find_credentials(self):
        """The find_credentials method calls proper method."""
        yield self.do_test(self.cred_tool.find_credentials, {})

    @defer.inlineCallbacks
    def test_register(self):
        """The register method calls proper method."""
        yield self.do_test(self.cred_tool.register, FAKED_CREDENTIALS,
                           **self.window_id_arg)

    @defer.inlineCallbacks
    def test_register_authorization_denied(self):
        """The register method calls proper method."""
        self.token = {}
        yield self.do_test(self.cred_tool.register, None,
                           **self.window_id_arg)

    @defer.inlineCallbacks
    def test_login(self):
        """The login method calls proper method."""
        yield self.do_test(self.cred_tool.login, FAKED_CREDENTIALS,
                           **self.window_id_arg)

    @defer.inlineCallbacks
    def test_login_authorization_denied(self):
        """The login method calls proper method."""
        self.token = {}
        yield self.do_test(self.cred_tool.login, None, **self.window_id_arg)

    @defer.inlineCallbacks
    def test_login_email_password(self):
        """The login_email_password method calls proper method."""
        yield self.do_test(self.cred_tool.login_email_password,
                           FAKED_CREDENTIALS, **self.email_password_arg)


class WithCredentialsErrorTestCase(NoErrorNoCredsTestCase):
    """Test case when there was a CredentialsError sent from the proxy."""

    error_dict = expected = {'error_type': 'Test'}

    @defer.inlineCallbacks
    def do_test(self, method, expected=None, **kwargs):
        """Perform the test itself."""
        exc = yield self.assertFailure(method(**kwargs), Exception)
        self.assertIsInstance(exc, CredentialsError)
        self.assertEqual(self.expected, exc.args[0])


class WithErrorHandlerCalledTestCase(WithCredentialsErrorTestCase):
    """Test case when the error handler was called."""

    error_dict = None
    error_handler = expected = {'error_type': 'Another Test'}


class SignalsRemovedTestCase(NoErrorWithCredsTestCase):

    @defer.inlineCallbacks
    def do_test(self, method, expected=None, **kwargs):
        """Perform the test itself."""
        yield method(**kwargs)
        for signal in self.proxy._signals:
            self.assertTrue(signal.removed)


class PingURLPlatformDetails(TestCase):

    def test_ping_url(self):
        """The PING_URL is BASE_PING_URL plus urlencoded platform data."""
        result = urlparse.urlparse(PING_URL)

        expected_base = urlparse.urljoin(result.scheme + '://' + result.netloc,
                                         result.path)
        self.assertEqual(expected_base, BASE_PING_URL)

        expected_query = dict(urlparse.parse_qsl(result.query))
        expected_query = urllib.urlencode(expected_query)
        self.assertEqual(expected_query, platform_data())

    def test_ping_url_is_unicode(self):
        """The PING_URL is unicode."""
        self.assertIsInstance(PING_URL, unicode)

    def test_platform_data(self):
        """The platform data is correct."""
        expected = {"platform": platform.system(),
                    "platform_version": platform.release(),
                    "platform_arch": platform.machine(),
                    "client_version": clientdefs.VERSION}
        self.assertEqual(urllib.urlencode(expected), platform_data())

    def test_platform_data_non_ascii(self):
        """The platform data is correct for non ascii values."""
        system = u'Ñandú'
        release = u'ñoño'
        machine = u'rápida'
        version = u'1.2.3-ubuntu♥'

        self.patch(platform, 'system', lambda: system.encode('utf8'))
        self.patch(platform, 'release', lambda: release.encode('utf8'))
        self.patch(platform, 'machine', lambda: machine.encode('utf8'))
        self.patch(clientdefs, 'VERSION', version.encode('utf8'))

        expected = {"platform": system.encode('utf8'),
                    "platform_version": release.encode('utf8'),
                    "platform_arch": machine.encode('utf8'),
                    "client_version": version.encode('utf8')}
        expected = urllib.urlencode(expected)
        self.assertEqual(expected, platform_data())
