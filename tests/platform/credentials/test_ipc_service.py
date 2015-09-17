# -*- coding: utf-8 -*-
#
# Author: Alejandro J. Cura <alecu@canonical.com>
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
"""Tests for the Ubuntu One credentials management IPC service."""

import logging

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from contrib.testing.testcase import FAKED_CREDENTIALS
from ubuntuone.devtools.handlers import MementoHandler
from ubuntuone.platform.credentials import APP_NAME
from ubuntuone.platform.credentials.ipc_service import (
    CredentialsManagement,
    RemovableSignal,
    logger,
)

TEST_APP_NAME = "test application"
TEST_ERROR_DICT = {}
TEST_CREDENTIALS = FAKED_CREDENTIALS


class FakeSSOProxy(object):
    """A fake SSOProxy."""

    def __init__(self):
        """Initialize this fake."""
        signals = [
            "credentials_stored",
            "credentials_cleared",
            "credentials_found",
            "credentials_not_found",
            "authorization_denied",
            "credentials_error",
        ]
        for s in signals:
            handler_name = "on_%s" % s
            callback_name = "on_%s_cb" % s

            def make_handler(callback_name):
                """Create a handler for a given callback_name."""

                def handler(*args):
                    """A signal was called."""
                    callback = getattr(self, callback_name, None)
                    if callback is not None:
                        callback(*args)

                return handler

            setattr(self, handler_name, make_handler(callback_name))
            setattr(self, callback_name, None)


    def find_credentials(self, app_name, options):
        """Ask the U1 credentials."""
        return defer.succeed(TEST_CREDENTIALS)

    def clear_credentials(self, app_name, options):
        """Clear the U1 credentials."""
        return defer.succeed(None)

    def store_credentials(self, app_name, options):
        """Store the U1 credentials."""
        return defer.succeed(None)

    def register(self, app_name, options):
        """Register."""
        return defer.succeed(None)

    def login(self, app_name, options):
        """Login."""
        return defer.succeed(None)

    def login_email_password(self, app_name, options):
        """Login using email and password."""
        return defer.succeed(None)


class RemovableSignalTestCase(TestCase):
    """Tests for RemovableSignal."""

    @defer.inlineCallbacks
    def setUp(self):
        yield super(RemovableSignalTestCase, self).setUp()
        self.proxy = FakeSSOProxy()

    def test_creation(self):
        """When creating, bind properly to self.proxy."""
        rs = RemovableSignal(self.proxy, "test", lambda *a: None)
        self.assertIs(self.proxy.test, rs)

    def test_dunder_callable(self):
        """__call__ works as expected."""
        sample_store = []
        expected = object()
        test_cb = lambda res: sample_store.append(res)
        rs = RemovableSignal(self.proxy, "on_credentials_found_cb", test_cb)
        rs(APP_NAME, expected)
        self.assertEqual(sample_store, [expected])

    def test_callable_does_not_log_args(self):
        """__call__ does not log its arguments."""
        self.handler = MementoHandler()
        self.handler.setLevel(logging.DEBUG)
        logger.addHandler(self.handler)
        self.addCleanup(logger.removeHandler, self.handler)

        secret_token = "secret token!"
        test_cb = lambda _: None
        rs = RemovableSignal(self.proxy, "on_credentials_found_cb", test_cb)

        rs(APP_NAME, {"secret": secret_token})
        for record in self.handler.records:
            self.assertNotIn(secret_token, record.message)

    def test_dunder_filters_other_apps(self):
        """__call__ filters by app_name."""
        sample_store = []
        test_cb = lambda res: sample_store.append(res)
        rs = RemovableSignal(self.proxy, "on_credentials_found_cb", test_cb)
        rs('other app name', object())
        self.assertEqual(sample_store, [])

    def test_remove(self):
        """The signal has a .remove that removes the callback."""
        sample_store = []
        test_cb = lambda app_name, creds: sample_store.append(creds)
        rs = RemovableSignal(self.proxy, "on_credentials_found_cb", test_cb)
        rs.remove()
        rs(TEST_APP_NAME, TEST_CREDENTIALS)
        self.assertEqual(len(sample_store), 0)


class CredentialsManagementTestCase(TestCase):
    """Tests for CredentialsManagement."""

    timeout = 5
    app_name = APP_NAME

    @defer.inlineCallbacks
    def setUp(self):
        yield super(CredentialsManagementTestCase, self).setUp()
        self._called = False
        self.proxy = FakeSSOProxy()
        self.cm = CredentialsManagement(self.proxy)

    def _set_called(self, *args, **kwargs):
        """Helper to keep track calls."""
        self._called = (args, kwargs)

    def assert_callback_called(self, expected):
        """Test that _called helper holds 'expected'."""
        self.assertEqual(self._called, expected)

    def test_find_credentials(self):
        """Test the find_credentials method."""
        d = defer.Deferred()
        ok = lambda: d.callback("ok")
        error = lambda *args: d.errback(args)
        self.cm.find_credentials(reply_handler=ok, error_handler=error)
        return d

    def test_clear_credentials(self):
        """Test the clear_credentials method."""
        d = defer.Deferred()
        ok = lambda: d.callback("ok")
        error = lambda *args: d.errback(args)
        self.cm.clear_credentials(reply_handler=ok, error_handler=error)
        return d

    def test_store_credentials(self):
        """Test the store_credentials method."""
        d = defer.Deferred()
        ok = lambda: d.callback("ok")
        error = lambda *args: d.errback(args)
        self.cm.store_credentials(TEST_CREDENTIALS, reply_handler=ok,
                                  error_handler=error)
        return d

    def test_register(self):
        """Test the register method."""
        d = defer.Deferred()
        ok = lambda: d.callback("ok")
        error = lambda *args: d.errback(args)
        self.cm.register({}, reply_handler=ok, error_handler=error)
        return d

    def test_login(self):
        """Test the login method."""
        d = defer.Deferred()
        ok = lambda: d.callback("ok")
        error = lambda *args: d.errback(args)
        self.cm.login({}, reply_handler=ok, error_handler=error)
        return d

    def test_login_email_password(self):
        """Test the login_email_password method."""
        d = defer.Deferred()
        ok = lambda: d.callback("ok")
        error = lambda *args: d.errback(args)
        self.cm.login_email_password({'email': 'foo', 'password': 'bar'},
                                     reply_handler=ok, error_handler=error)
        return d

    def test_register_to_credentials_found(self):
        """Test the register_to_credentials_found method."""
        signal = self.cm.register_to_credentials_found(self._set_called)
        signal(self.app_name, TEST_CREDENTIALS)
        self.assert_callback_called(((TEST_CREDENTIALS,), {}))

    def test_register_to_credentials_not_found(self):
        """Test the register_to_credentials_not_found method."""
        signal = self.cm.register_to_credentials_not_found(self._set_called)
        signal(self.app_name)
        self.assert_callback_called(((), {}))

    def test_register_to_credentials_stored(self):
        """Test the register_to_credentials_stored method."""
        signal = self.cm.register_to_credentials_stored(self._set_called)
        signal(self.app_name)
        self.assert_callback_called(((), {}))

    def test_register_to_credentials_cleared(self):
        """Test the register_to_credentials_cleared method."""
        signal = self.cm.register_to_credentials_cleared(self._set_called)
        signal(self.app_name)
        self.assert_callback_called(((), {}))

    def test_register_to_credentials_error(self):
        """Test the register_to_credentials_error method."""
        signal = self.cm.register_to_credentials_error(self._set_called)
        signal(self.app_name)
        self.assert_callback_called(((), {}))

    def test_register_to_authorization_denied(self):
        """Test the register_to_authorization_denied method."""
        signal = self.cm.register_to_authorization_denied(self._set_called)
        signal(self.app_name, TEST_ERROR_DICT)
        self.assert_callback_called(((TEST_ERROR_DICT,), {}))

    def _verify_not_called_twice(self, signal_name, *args):
        """Test that the callback is not called twice."""
        d = defer.Deferred()

        def signal_handler(*args):
            """Fake the behaviour of CredentialsManagementTool."""
            d.callback(args[0] if len(args) > 0 else None)

        register = getattr(self.cm, "register_to_" + signal_name)
        signal = register(signal_handler)
        proxy_cb = getattr(self.proxy, "on_" + signal_name)
        proxy_cb(*args)
        if getattr(signal, "remove", False):
            signal.remove()
        proxy_cb(*args)

    def test_not_called_twice_credentials_stored(self):
        """Test that on_credentials_stored is not called twice."""
        self._verify_not_called_twice("credentials_stored")

    def test_not_called_twice_credentials_cleared(self):
        """Test that on_credentials_cleared is not called twice."""
        self._verify_not_called_twice("credentials_cleared")

    def test_not_called_twice_credentials_found(self):
        """Test that on_credentials_found is not called twice."""
        self._verify_not_called_twice("credentials_found", self.app_name,
                                      TEST_CREDENTIALS)

    def test_not_called_twice_credentials_not_found(self):
        """Test that on_credentials_not_found is not called twice."""
        self._verify_not_called_twice("credentials_not_found")

    def test_not_called_twice_authorization_denied(self):
        """Test that on_authorization_denied is not called twice."""
        self._verify_not_called_twice("authorization_denied")

    def test_not_called_twice_credentials_error(self):
        """Test that on_credentials_error is not called twice."""
        self._verify_not_called_twice("credentials_error", TEST_ERROR_DICT)

    def test_connect_to_signal(self):
        """The connect_to_signal method is correct."""
        for signal_name in self.cm._SIGNAL_TO_CALLBACK_MAPPING:
            match = self.cm.connect_to_signal(signal_name, self._set_called)
            expected = object()
            match(APP_NAME, expected)
            self.assertEqual(self._called, ((expected,), {}))


class CredentialsManagementOtherAppNameTestCase(CredentialsManagementTestCase):
    """Tests for CredentialsManagement when the app name differs."""

    app_name = 'other app name'

    def assert_callback_called(self, expected):
        """Test that _called helper does not hold 'expected'."""
        self.assertEqual(self._called, False)
