# -*- coding: utf-8 -*-
#
# Author: Natalia B. Bidart <natalia.bidart@canonical.com>
#
# Copyright 2010-2012 Canonical Ltd.
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
"""Tests for the Ubuntu One credentials management dbus service."""

import logging

from functools import wraps

import dbus.service

from twisted.internet.defer import Deferred, inlineCallbacks
from ubuntuone.devtools.handlers import MementoHandler
from ubuntuone.devtools.testcases import skipTest
from ubuntuone.devtools.testcases.dbus import DBusTestCase

from ubuntuone.platform.credentials import (
    CredentialsError,
    CredentialsManagementTool,
    logger,
    UI_PARAMS,
)
from ubuntuone.platform.credentials.dbus_service import (
    APP_NAME,
    CredentialsManagement,
    dbus,
    DBUS_BUS_NAME,
    DBUS_CREDENTIALS_IFACE,
    DBUS_CREDENTIALS_PATH,
    TIMEOUT_INTERVAL,
    ubuntu_sso,
)

FAKED_CREDENTIALS = {
    'consumer_key': 'faked_consumer_key',
    'consumer_secret': 'faked_consumer_secret',
    'token': 'faked_token',
    'token_secret': 'faked_token_secret',
    'token_name': 'Woohoo test',
}


class FakedSSOService(dbus.service.Object):
    """Faked DBus object that manages credentials."""

    error_dict = None
    app_name = None

    def __init__(self, *args, **kwargs):
        super(FakedSSOService, self).__init__(*args, **kwargs)
        self._credentials = {}
        self._args = None
        self._kwargs = None

    def maybe_emit_error(f):
        """Decorator to fake a CredentialsError signal."""

        @wraps(f)
        def inner(self, *args, **kwargs):
            """Fake a CredentialsError signal."""
            if FakedSSOService.error_dict is not None:
                if 'error_handler' in kwargs:
                    error_handler = kwargs['error_handler']
                    exc = dbus.service.DBusException(FakedSSOService.error_dict)
                    error_handler(exc)
                else:
                    self.CredentialsError(FakedSSOService.app_name,
                                          FakedSSOService.error_dict)
            else:
                return f(self, *args, **kwargs)

        return inner

    def store_args(f):
        """Decorator to store arguments to check correct calls."""

        @wraps(f)
        def inner(self, app_name, args, **kwargs):
            """Store arguments to check correct calls."""
            self._app_name = app_name
            self._args = args
            self._kwargs = kwargs
            return f(self, app_name, args, **kwargs)

        return inner

    @dbus.service.signal(ubuntu_sso.DBUS_CREDENTIALS_IFACE, signature='s')
    def AuthorizationDenied(self, app_name):
        """Signal thrown when the user denies the authorization."""

    @dbus.service.signal(ubuntu_sso.DBUS_CREDENTIALS_IFACE, signature='sa{ss}')
    def CredentialsFound(self, app_name, credentials):
        """Signal thrown when the credentials are found."""

    @dbus.service.signal(ubuntu_sso.DBUS_CREDENTIALS_IFACE, signature='s')
    def CredentialsNotFound(self, app_name):
        """Signal thrown when the credentials are not found."""

    @dbus.service.signal(ubuntu_sso.DBUS_CREDENTIALS_IFACE, signature='s')
    def CredentialsCleared(self, app_name):
        """Signal thrown when the credentials were cleared."""

    @dbus.service.signal(ubuntu_sso.DBUS_CREDENTIALS_IFACE, signature='s')
    def CredentialsStored(self, app_name):
        """Signal thrown when the credentials were cleared."""

    @dbus.service.signal(ubuntu_sso.DBUS_CREDENTIALS_IFACE, signature='sa{ss}')
    def CredentialsError(self, app_name, error_dict):
        """Signal thrown when there is a problem getting the credentials."""

    @store_args
    @maybe_emit_error
    @dbus.service.method(dbus_interface=ubuntu_sso.DBUS_CREDENTIALS_IFACE,
                         in_signature='sa{ss}', out_signature='')
    def find_credentials(self, app_name, args):
        """Look for the credentials for an application."""
        creds = self._credentials.get(FakedSSOService.app_name, None)
        if creds is not None:
            self.CredentialsFound(FakedSSOService.app_name, creds)
        else:
            self.CredentialsNotFound(FakedSSOService.app_name)

    @store_args
    @maybe_emit_error
    @dbus.service.method(dbus_interface=ubuntu_sso.DBUS_CREDENTIALS_IFACE,
                         in_signature='sa{ss}', out_signature='a{ss}',
                         async_callbacks=('reply_handler', 'error_handler'))
    def find_credentials_sync(self, app_name, args,
                              reply_handler=None, error_handler=None):
        """Look for the credentials for an application."""
        creds = self._credentials.get(FakedSSOService.app_name, None)
        if creds is None:
            creds = {}
        if reply_handler is not None:
            reply_handler(creds)
        else:
            return creds

    @store_args
    @maybe_emit_error
    @dbus.service.method(dbus_interface=ubuntu_sso.DBUS_CREDENTIALS_IFACE,
                         in_signature='sa{ss}', out_signature='')
    def clear_credentials(self, app_name, args):
        """Clear the credentials for an application."""
        self._credentials.pop(FakedSSOService.app_name, None)
        self.CredentialsCleared(FakedSSOService.app_name)

    @store_args
    @maybe_emit_error
    @dbus.service.method(dbus_interface=ubuntu_sso.DBUS_CREDENTIALS_IFACE,
                         in_signature='sa{ss}', out_signature='')
    def store_credentials(self, app_name, args):
        """Store the token for an application."""
        self._credentials[FakedSSOService.app_name] = args
        self.CredentialsStored(FakedSSOService.app_name)

    @store_args
    @maybe_emit_error
    @dbus.service.method(dbus_interface=ubuntu_sso.DBUS_CREDENTIALS_IFACE,
                         in_signature='sa{ss}', out_signature='')
    def register(self, app_name, args):
        """Get credentials if found else prompt GUI to register."""
        creds = self._credentials.get(FakedSSOService.app_name, None)
        if creds is not None and len(creds) > 0:
            self.CredentialsFound(FakedSSOService.app_name, creds)
        elif creds == {}:
            # fake an AuthorizationDenied
            self.AuthorizationDenied(FakedSSOService.app_name)
        elif creds is None:
            # fake the adding of the credentials, in reality this will bring
            # a GUI that the user will interact with.
            self._credentials[FakedSSOService.app_name] = FAKED_CREDENTIALS
            self.CredentialsFound(FakedSSOService.app_name, FAKED_CREDENTIALS)

    @store_args
    @maybe_emit_error
    @dbus.service.method(dbus_interface=ubuntu_sso.DBUS_CREDENTIALS_IFACE,
                         in_signature='sa{ss}', out_signature='')
    def login(self, app_name, args):
        """Get credentials if found else prompt GUI to login."""
        self.register(app_name, args)


class BaseTestCase(DBusTestCase):
    """Base test case."""

    timeout = 8
    app_name = APP_NAME
    error_dict = None

    @inlineCallbacks
    def setUp(self):
        yield super(BaseTestCase, self).setUp()
        FakedSSOService.app_name = self.app_name
        FakedSSOService.error_dict = self.error_dict

        self.memento = MementoHandler()
        self.memento.setLevel(logging.DEBUG)
        logger.addHandler(self.memento)

        self.sso_server = self.register_server(ubuntu_sso.DBUS_BUS_NAME,
                                ubuntu_sso.DBUS_CREDENTIALS_PATH,
                                FakedSSOService)  # faked SSO server
        self.args = {'window_id': '803'}

    def register_server(self, bus_name, object_path, service_class):
        """Register a service on the session bus."""
        name = self.bus.request_name(bus_name, dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
        self.assertNotEqual(name, dbus.bus.REQUEST_NAME_REPLY_EXISTS,
                            'Service %s should not be running.' % bus_name)
        mock = service_class(object_path=object_path, conn=self.bus)
        self.addCleanup(mock.remove_from_connection)
        self.addCleanup(self.bus.release_name, bus_name)

        return mock

    def get_proxy(self, bus_name, object_path, dbus_interface):
        obj = self.bus.get_object(bus_name=bus_name, object_path=object_path,
                                  follow_name_owner_changes=True)
        proxy = dbus.Interface(object=obj, dbus_interface=dbus_interface)
        return proxy

    def get_sso_proxy(self):
        return self.get_proxy(bus_name=ubuntu_sso.DBUS_BUS_NAME,
                              object_path=ubuntu_sso.DBUS_CREDENTIALS_PATH,
                              dbus_interface=ubuntu_sso.DBUS_CREDENTIALS_IFACE)


class CredentialsManagementTestCase(BaseTestCase):
    """Test case for the DBus object that manages Ubuntu One credentials."""

    signals = ('CredentialsFound', 'CredentialsNotFound', 'CredentialsCleared',
               'CredentialsStored', 'CredentialsError', 'AuthorizationDenied')

    @inlineCallbacks
    def setUp(self):
        yield super(CredentialsManagementTestCase, self).setUp()
        self.creds_server = self.register_server(DBUS_BUS_NAME,
                                DBUS_CREDENTIALS_PATH,
                                CredentialsManagement)  # real service

        self.deferred = Deferred()
        self.proxy = self.get_creds_proxy()

    def get_creds_proxy(self):
        return self.get_proxy(bus_name=DBUS_BUS_NAME,
                              object_path=DBUS_CREDENTIALS_PATH,
                              dbus_interface=DBUS_CREDENTIALS_IFACE)

    def connect_signals(self, callback=None):
        """Connect every signal accordingly to fire self.deferred.

        If 'callback' is not None, it will be used as a tuple (sig_name,
        function) and 'sig_name' will be connected to 'function', which should
        fire self.deferred properly.

        """
        success_sig_name, success_function = None, None
        if callback is not None:
            success_sig_name, success_function = callback

        def fail(sig_name):
            """Decorator to fire self.deferred."""
            def inner(*args, **kwargs):
                """Fire self.deferred."""
                msg = 'Received an unexpected signal (%r).' % sig_name
                self.deferred.errback(TypeError(msg))
            return inner

        for sig_name in self.signals:
            if sig_name == success_sig_name:
                sig = self.proxy.connect_to_signal(sig_name, success_function)
            else:
                sig = self.proxy.connect_to_signal(sig_name, fail(sig_name))
            self.addCleanup(sig.remove)

    @inlineCallbacks
    def add_credentials(self, creds=FAKED_CREDENTIALS):
        """Add some fake credentials for 'self.app_name'."""
        d = Deferred()
        sso_proxy = self.get_sso_proxy()
        sso_proxy.store_credentials(self.app_name, creds,
                                    reply_handler=lambda: d.callback(None),
                                    error_handler=d.errback)
        yield d

    @inlineCallbacks
    def do_test(self):
        """Perform the test itself."""
        yield self.deferred

    def test_get_sso_proxy(self):
        """The SSO dbus proxy is properly retrieved."""
        sso_proxy = CredentialsManagement().sso_proxy
        self.assertEqual(sso_proxy.bus_name, ubuntu_sso.DBUS_BUS_NAME)
        self.assertEqual(sso_proxy.object_path,
                         ubuntu_sso.DBUS_CREDENTIALS_PATH)
        self.assertEqual(sso_proxy.dbus_interface,
                         ubuntu_sso.DBUS_CREDENTIALS_IFACE)


class ArgsTestCase(CredentialsManagementTestCase):
    """Test case to check that proper arguments are passed to SSO backend."""

    @inlineCallbacks
    def test_find_credentials(self):
        """The find_credentials method calls ubuntu_sso's method."""
        d = Deferred()
        self.proxy.find_credentials(reply_handler=lambda: d.callback(None),
                                    error_handler=d.errback)
        yield d

        self.assertEqual(self.sso_server._app_name, APP_NAME)
        self.assertEqual(self.sso_server._args, {})

    @inlineCallbacks
    def test_find_credentials_sync(self):
        """The find_credentials_sync method calls ubuntu_sso's method."""
        d = Deferred()
        self.proxy.find_credentials_sync(reply_handler=d.callback,
                                         error_handler=lambda *a: d.errback(a))
        yield d

        self.assertEqual(self.sso_server._app_name, APP_NAME)
        self.assertEqual(self.sso_server._args, {})
        self.assertTrue('reply_handler' in self.sso_server._kwargs)
        self.assertTrue('error_handler' in self.sso_server._kwargs)

    @inlineCallbacks
    def test_clear_credentials(self):
        """The clear_credentials method calls ubuntu_sso's method."""
        d = Deferred()
        self.proxy.clear_credentials(reply_handler=lambda: d.callback(None),
                                     error_handler=d.errback)
        yield d

        self.assertEqual(self.sso_server._app_name, APP_NAME)
        self.assertEqual(self.sso_server._args, {})

    @inlineCallbacks
    def test_store_credentials(self):
        """The store_credentials method calls ubuntu_sso's method."""
        d = Deferred()
        self.proxy.store_credentials(FAKED_CREDENTIALS,
                                     reply_handler=lambda: d.callback(None),
                                     error_handler=d.errback)
        yield d

        self.assertEqual(self.sso_server._app_name, APP_NAME)
        self.assertEqual(self.sso_server._args, FAKED_CREDENTIALS)

    @inlineCallbacks
    def test_register(self):
        """The register method calls ubuntu_sso's method."""
        d = Deferred()
        self.proxy.register(self.args, reply_handler=lambda: d.callback(None),
                            error_handler=d.errback)
        yield d

        self.assertEqual(self.sso_server._app_name, APP_NAME)
        # convert to unicode for the comparison, as the message is arriving
        # here as bytes (bad gettext usage!)
        params = dict((x, y.decode("utf8") if isinstance(y, str) else y)
                      for x, y in UI_PARAMS.items())
        params.update(self.args)
        self.assertEqual(self.sso_server._args, params)

    @inlineCallbacks
    def test_login(self):
        """The login method calls ubuntu_sso's method."""
        d = Deferred()
        self.proxy.login(self.args, reply_handler=lambda: d.callback(None),
                         error_handler=d.errback)
        yield d

        self.assertEqual(self.sso_server._app_name, APP_NAME)
        # convert to unicode for the comparison, as the message is arriving
        # here as bytes (bad gettext usage!)
        params = dict((x, y.decode("utf8") if isinstance(y, str) else y)
                      for x, y in UI_PARAMS.items())
        params.update(self.args)
        self.assertEqual(self.sso_server._args, params)


class DictSignatureTestCase(DBusTestCase):
    """Test the errors with dict signatures."""

    def verify(self, app_name, options_dict, reply_handler, error_handler):
        """Verify that the options_dict is a dbus.Dictionary."""
        self.assertIsInstance(options_dict, dbus.Dictionary)

    def test_find_credentials_dict_signature(self):
        """Test for find_credentials."""
        creds_man = CredentialsManagement()
        self.patch(creds_man.sso_proxy, "find_credentials", self.verify)
        creds_man.find_credentials()

    def test_find_credentials_sync_dict_signature(self):
        """Test for find_credentials_sync."""
        creds_man = CredentialsManagement()
        self.patch(creds_man.sso_proxy, "find_credentials_sync", self.verify)
        creds_man.find_credentials_sync()

    def test_clear_credentials_dict_signature(self):
        """Test for clear_credentials."""
        creds_man = CredentialsManagement()
        self.patch(creds_man.sso_proxy, "clear_credentials", self.verify)
        creds_man.clear_credentials()


class SameAppNoErrorTestCase(CredentialsManagementTestCase):
    """Test case when the app_name matches APP_NAME and there was no error."""

    @inlineCallbacks
    def test_find_credentials(self):
        """The find_credentials method calls ubuntu_sso's method."""
        d = Deferred()
        yield self.add_credentials()

        def verify(credentials):
            """Do the check."""
            self.assertEqual(credentials, FAKED_CREDENTIALS)
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsFound', verify))

        self.proxy.find_credentials(reply_handler=lambda: d.callback(None),
                                    error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_find_credentials_sync(self):
        """The find_credentials_sync method calls ubuntu_sso's method."""
        yield self.add_credentials()

        def verify(credentials):
            """Do the check."""
            self.assertEqual(credentials, FAKED_CREDENTIALS)
            self.deferred.callback(None)

        error_handler = lambda a: self.deferred.errback(a)
        self.proxy.find_credentials_sync(reply_handler=verify,
                                         error_handler=error_handler)
        yield self.do_test()

    @inlineCallbacks
    def test_find_credentials_without_credentials(self):
        """The find_credentials method calls ubuntu_sso's method."""
        d = Deferred()

        def verify():
            """Do the check."""
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsNotFound', verify))

        self.proxy.find_credentials(reply_handler=lambda: d.callback(None),
                                    error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_clear_credentials(self):
        """The clear_credentials method calls ubuntu_sso's method."""
        d = Deferred()
        yield self.add_credentials()

        def verify():
            """Do the check."""
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsCleared', verify))

        self.proxy.clear_credentials(reply_handler=lambda: d.callback(None),
                                     error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_clear_credentials_without_credentials(self):
        """The clear_credentials method calls ubuntu_sso's method."""
        d = Deferred()

        def verify():
            """Do the check."""
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsCleared', verify))

        self.proxy.clear_credentials(reply_handler=lambda: d.callback(None),
                                     error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_store_credentials(self):
        """The store_credentials method calls ubuntu_sso's method."""
        d = Deferred()

        def verify():
            """Do the check."""
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsStored', verify))

        self.proxy.store_credentials(FAKED_CREDENTIALS,
                                     reply_handler=lambda: d.callback(None),
                                     error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_register_with_credentials(self):
        """The register method calls ubuntu_sso's method."""
        d = Deferred()
        yield self.add_credentials()

        def verify(credentials):
            """Do the check."""
            self.assertEqual(credentials, FAKED_CREDENTIALS)
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsFound', verify))

        self.proxy.register(self.args, reply_handler=lambda: d.callback(None),
                            error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_register_without_credentials(self):
        """The register method calls ubuntu_sso's method."""
        d = Deferred()

        def verify(credentials):
            """Do the check."""
            self.assertEqual(credentials, FAKED_CREDENTIALS)
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsFound', verify))

        self.proxy.register(self.args, reply_handler=lambda: d.callback(None),
                            error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_register_authorization_denied(self):
        """The register method calls ubuntu_sso's method."""
        d = Deferred()
        yield self.add_credentials(creds={})

        def verify():
            """Do the check."""
            self.deferred.callback(None)

        self.connect_signals(callback=('AuthorizationDenied', verify))

        self.proxy.register(self.args, reply_handler=lambda: d.callback(None),
                            error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_login_with_credentials(self):
        """The login method calls ubuntu_sso's method."""
        d = Deferred()
        yield self.add_credentials()

        def verify(credentials):
            """Do the check."""
            self.assertEqual(credentials, FAKED_CREDENTIALS)
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsFound', verify))

        self.proxy.login(self.args, reply_handler=lambda: d.callback(None),
                         error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_login_without_credentials(self):
        """The login method calls ubuntu_sso's method."""
        d = Deferred()

        def verify(credentials):
            """Do the check."""
            self.assertEqual(credentials, FAKED_CREDENTIALS)
            self.deferred.callback(None)

        self.connect_signals(callback=('CredentialsFound', verify))

        self.proxy.login(self.args, reply_handler=lambda: d.callback(None),
                         error_handler=d.errback)
        yield d
        yield self.do_test()

    @inlineCallbacks
    def test_login_authorization_denied(self):
        """The login method calls ubuntu_sso's method."""
        d = Deferred()
        yield self.add_credentials(creds={})

        def verify():
            """Do the check."""
            self.deferred.callback(None)

        self.connect_signals(callback=('AuthorizationDenied', verify))

        self.proxy.login(self.args, reply_handler=lambda: d.callback(None),
                         error_handler=d.errback)
        yield d
        yield self.do_test()


class SameAppWithErrorTestCase(SameAppNoErrorTestCase):
    """Test case when the app_name matches APP_NAME and there was an error."""

    error_dict = {'error_type': 'Test'}

    def connect_signals(self, callback=None):
        """CredentialsError is the success signals in this suite."""

        def verify(error_dict):
            """Do the check."""
            self.assertEqual(error_dict, self.error_dict)
            self.deferred.callback(error_dict)

        args = ('CredentialsError', verify)
        super(SameAppWithErrorTestCase, self).connect_signals(callback=args)

    @skipTest('Failing on Ubuntu 13.04 - bug #1085204')
    @inlineCallbacks
    def test_find_credentials_sync(self):
        """The find_credentials_sync method calls ubuntu_sso's method."""

        def verify(error):
            """Do the check."""
            try:
                self.assertEqual(error.args[0], str(self.error_dict))
            except Exception, e:
                self.deferred.errback(e)
            else:
                self.deferred.callback(None)

        self.proxy.find_credentials_sync(reply_handler=self.deferred.errback,
                                         error_handler=verify)
        yield self.do_test()


class OtherAppNoErrorTestCase(SameAppNoErrorTestCase):
    """Test case when the app_name is not APP_NAME and there was no error."""

    app_name = APP_NAME * 2

    def connect_signals(self, callback=None):
        """No signal should be received in this suite."""
        # ignore all success connection, self.deferred should always errback
        super(OtherAppNoErrorTestCase, self).connect_signals(callback=None)

    @inlineCallbacks
    def do_test(self):
        """Perform the test itself."""
        if not self.deferred.called:
            msg = 'does not match %r, exiting.' % APP_NAME
            if self.memento.check_info(self.app_name, msg):
                self.deferred.callback(None)
            else:
                self.deferred.errback('Log should be present.')

        yield self.deferred


class OtherAppWithErrorTestCase(OtherAppNoErrorTestCase):
    """Test case when the app_name is not APP_NAME and there was an error."""

    app_name = APP_NAME * 2
    error_dict = {'error_type': 'Test'}

    def test_find_credentials_sync(self):
        """This test has no sense for a synchronous method."""


class RefCountingTestCase(BaseTestCase):
    """Tests for the CredentialsManagement ref counting."""

    @inlineCallbacks
    def setUp(self):
        yield super(RefCountingTestCase, self).setUp()
        self._called = False
        self.client = CredentialsManagement()

    def _set_called(self, *args, **kwargs):
        """Keep track of method calls."""
        self._called = (args, kwargs)

    def test_ref_counting(self):
        """Ref counting is in place."""
        self.assertEqual(self.client.ref_count, 0)

    def test_find_credentials(self):
        """Keep proper track of on going requests."""
        d = Deferred()

        def verify(*args):
            """Make the check."""
            self.assertEqual(self.client.ref_count, 1)
            d.callback(True)

        self.patch(self.client, 'CredentialsNotFound', verify)
        self.client.find_credentials()

        return d

    def test_find_credentials_sync(self):
        """Keep proper track of on going requests."""
        d = Deferred()

        def verify(*args):
            """Make the check."""
            self.assertEqual(self.client.ref_count, 1)
            d.callback(True)

        self.client.find_credentials_sync(reply_handler=verify,
                                          error_handler=d.errback)
        return d

    def test_find_credentials_sync_error(self):
        """Keep proper track of on going requests."""
        d = Deferred()

        def verify(*args):
            """Make the check."""
            self.assertEqual(self.client.ref_count, 1)
            d.callback(True)

        self.patch(FakedSSOService, 'error_dict', 'foo')
        self.client.find_credentials_sync(reply_handler=d.errback,
                                          error_handler=verify)

        return d

    def test_clear_credentials(self):
        """Keep proper track of on going requests."""
        d = Deferred()

        def verify(*args):
            """Make the check."""
            self.assertEqual(self.client.ref_count, 1)
            d.callback(True)

        self.patch(self.client, 'CredentialsCleared', verify)
        self.client.clear_credentials()

        return d

    def test_store_credentials(self):
        """Keep proper track of on going requests."""
        d = Deferred()

        def verify(*args):
            """Make the check."""
            self.assertEqual(self.client.ref_count, 1)
            d.callback(True)

        self.patch(self.client, 'CredentialsStored', verify)
        self.client.store_credentials(self.args)

        return d

    def test_register(self):
        """Keep proper track of on going requests."""
        d = Deferred()

        def verify(*args):
            """Make the check."""
            self.assertEqual(self.client.ref_count, 1)
            d.callback(True)

        self.patch(self.client, 'CredentialsFound', verify)
        self.client.register(self.args)

        return d

    def test_login(self):
        """Keep proper track of on going requests."""
        d = Deferred()

        def verify(*args):
            """Make the check."""
            self.assertEqual(self.client.ref_count, 1)
            d.callback(True)

        self.patch(self.client, 'CredentialsFound', verify)
        self.client.login(self.args)

        return d

    def test_several_requests(self):
        """Requests can be nested."""
        d = Deferred()

        self.ref_count = 0

        def parallel_counter(*args):
            """Make the check."""
            self.ref_count += 1
            if self.ref_count == 5:
                self.assertEqual(self.client.ref_count, self.ref_count)
                d.callback(True)

        self.patch(self.client, 'CredentialsFound', parallel_counter)

        self.client.login(self.args)
        self.client.register(self.args)
        self.client.login(self.args)
        self.client.register(self.args)
        self.client.register(self.args)

        return d

    def test_credentials_found(self):
        """Ref counter is decreased when a signal is sent."""
        self.client.ref_count = 3
        self.client.CredentialsFound(FAKED_CREDENTIALS)

        self.assertEqual(self.client.ref_count, 2)

    def test_credentials_not_found(self):
        """Ref counter is decreased when a signal is sent."""
        self.client.ref_count = 3
        self.client.CredentialsNotFound()

        self.assertEqual(self.client.ref_count, 2)

    def test_credentials_cleared(self):
        """Ref counter is decreased when a signal is sent."""
        self.client.ref_count = 3
        self.client.CredentialsCleared()

        self.assertEqual(self.client.ref_count, 2)

    def test_credentials_stored(self):
        """Ref counter is decreased when a signal is sent."""
        self.client.ref_count = 3
        self.client.CredentialsStored()

        self.assertEqual(self.client.ref_count, 2)

    def test_credentials_error(self):
        """Ref counter is decreased when a signal is sent."""
        self.client.ref_count = 3
        self.client.CredentialsError({'error_type': 'test'})

        self.assertEqual(self.client.ref_count, 2)

    def test_authorization_denied(self):
        """Ref counter is decreased when a signal is sent."""
        self.client.ref_count = 3
        self.client.AuthorizationDenied()

        self.assertEqual(self.client.ref_count, 2)

    def test_credentials_found_when_ref_count_is_not_positive(self):
        """Ref counter is decreased when a signal is sent."""
        self.client._ref_count = -3
        self.client.CredentialsFound(FAKED_CREDENTIALS)

        self.assertEqual(self.client.ref_count, 0)
        msg = 'Attempting to decrease ref_count to a negative value (-4).'
        self.assertTrue(self.memento.check_warning(msg))

    def test_credentials_not_found_when_ref_count_is_not_positive(self):
        """Ref counter is decreased when a signal is sent."""
        self.client._ref_count = -3
        self.client.CredentialsNotFound()

        self.assertEqual(self.client.ref_count, 0)
        msg = 'Attempting to decrease ref_count to a negative value (-4).'
        self.assertTrue(self.memento.check_warning(msg))

    def test_credentials_cleared_when_ref_count_is_not_positive(self):
        """Ref counter is decreased when a signal is sent."""
        self.client._ref_count = -3
        self.client.CredentialsCleared()

        self.assertEqual(self.client.ref_count, 0)
        msg = 'Attempting to decrease ref_count to a negative value (-4).'
        self.assertTrue(self.memento.check_warning(msg))

    def test_credentials_stored_when_ref_count_is_not_positive(self):
        """Ref counter is decreased when a signal is sent."""
        self.client._ref_count = -3
        self.client.CredentialsStored()

        self.assertEqual(self.client.ref_count, 0)
        msg = 'Attempting to decrease ref_count to a negative value (-4).'
        self.assertTrue(self.memento.check_warning(msg))

    def test_credentials_error_when_ref_count_is_not_positive(self):
        """Ref counter is decreased when a signal is sent."""
        self.client._ref_count = -3
        self.client.CredentialsError({'error_type': 'test'})

        self.assertEqual(self.client.ref_count, 0)
        msg = 'Attempting to decrease ref_count to a negative value (-4).'
        self.assertTrue(self.memento.check_warning(msg))

    def test_autorization_denied_when_ref_count_is_not_positive(self):
        """Ref counter is decreased when a signal is sent."""
        self.client._ref_count = -3
        self.client.AuthorizationDenied()

        self.assertEqual(self.client.ref_count, 0)
        msg = 'Attempting to decrease ref_count to a negative value (-4).'
        self.assertTrue(self.memento.check_warning(msg))

    def test_on_zero_ref_count_shutdown(self):
        """When ref count reaches 0, queue shutdown op."""
        self.client.timeout_func = self._set_called
        self.client.login(self.args)
        self.client.CredentialsFound(FAKED_CREDENTIALS)

        self.assertEqual(self._called,
                         ((TIMEOUT_INTERVAL, self.client.shutdown), {}))

    def test_on_non_zero_ref_count_do_not_shutdown(self):
        """If ref count is not 0, do not queue shutdown op."""
        self.client.timeout_func = self._set_called
        self.client.login(self.args)

        self.assertEqual(self._called, False)

    def test_on_non_zero_ref_count_after_zero_do_not_shutdown(self):
        """If the shutdown was queued, do not quit if counter is not zero."""

        def fake_timeout_func(interval, func):
            """Start a new request when the timer is started."""
            self.client._ref_count = 1
            assert self.client.ref_count > 0
            func()

        self.client.timeout_func = fake_timeout_func
        self.client.shutdown_func = self._set_called

        self.client.ref_count = 0  # trigger timer and possible shutdown

        self.assertEqual(self._called, False, 'shutdown_func was not called')

    def test_zero_ref_count_after_zero_do_shutdown(self):
        """If the shutdown was queued, do quit if counter is zero."""

        def fake_timeout_func(interval, func):
            """Start a new request when the timer is started."""
            assert self.client.ref_count == 0
            func()

        self.client.timeout_func = fake_timeout_func
        self.client.shutdown_func = self._set_called

        self.client.ref_count = 0  # trigger timer and possible shutdown

        self.assertEqual(self._called, ((), {}), 'shutdown_func was called')


class CredentialsTestCase(BaseTestCase):
    """Test suite for the Credentials class."""

    @inlineCallbacks
    def setUp(self):
        yield super(CredentialsTestCase, self).setUp()
        FakedSSOService.error_dict = None
        self.creds_server = self.register_server(DBUS_BUS_NAME,
                                DBUS_CREDENTIALS_PATH,
                                CredentialsManagement)  # real service
        self.client = CredentialsManagementTool()

    @inlineCallbacks
    def test_find_credentials_no_credentials(self):
        """Find credentials when credentials does not exist."""
        result = yield self.client.find_credentials()

        self.assertEqual(result, {})

    @inlineCallbacks
    def test_find_credentials_with_credentials(self):
        """Find credentials when credentials exists."""
        yield self.client.store_credentials(FAKED_CREDENTIALS)

        result = yield self.client.find_credentials()

        self.assertEqual(result, FAKED_CREDENTIALS)

    @inlineCallbacks
    def test_find_credentials_error(self):
        """Find credentials and error."""
        FakedSSOService.error_dict = {'failure': 'really'}

        e = yield self.assertFailure(self.client.find_credentials(),
                                     CredentialsError)
        self.assertEqual(e[0], FakedSSOService.error_dict)

    @inlineCallbacks
    def test_clear_credentials(self):
        """Clear credentials."""
        yield self.client.store_credentials({'test': 'me'})
        yield self.client.clear_credentials()

        result = yield self.client.find_credentials()

        self.assertEqual(result, {})

    @inlineCallbacks
    def test_clear_credentials_error(self):
        """Clear credentials and error."""
        FakedSSOService.error_dict = {'failure': 'really'}

        e = yield self.assertFailure(self.client.clear_credentials(),
                                     CredentialsError)
        self.assertEqual(e[0], FakedSSOService.error_dict)

    @inlineCallbacks
    def test_store_credentials(self):
        """Store credentials."""
        token = {'test': 'me'}
        yield self.client.store_credentials(token)

        result = yield self.client.find_credentials()

        self.assertEqual(result, token)

    @inlineCallbacks
    def test_store_credentials_error(self):
        """Store credentials and error."""
        FakedSSOService.error_dict = {'failure': 'really'}

        e = yield self.assertFailure(self.client.store_credentials({'0': '1'}),
                                     CredentialsError)
        self.assertEqual(e[0], FakedSSOService.error_dict)

    @inlineCallbacks
    def test_register(self):
        """Register."""
        result = yield self.client.register()

        self.assertEqual(result, FAKED_CREDENTIALS)

    @inlineCallbacks
    def test_register_auth_denied(self):
        """Register and auth_denied."""
        yield self.client.store_credentials({})  # trigger AuthorizationDenied
        result = yield self.client.register()

        self.assertEqual(result, None)

    @inlineCallbacks
    def test_register_error(self):
        """Register and error."""
        FakedSSOService.error_dict = {'failure': 'really'}

        e = yield self.assertFailure(self.client.register(),
                                     CredentialsError)
        self.assertEqual(e[0], FakedSSOService.error_dict)

    @inlineCallbacks
    def test_login(self):
        """Login."""
        result = yield self.client.login()

        self.assertEqual(result, FAKED_CREDENTIALS)

    @inlineCallbacks
    def test_login_auth_denied(self):
        """Login and auth denied."""
        yield self.client.store_credentials({})  # trigger AuthorizationDenied
        result = yield self.client.login()

        self.assertEqual(result, None)

    @inlineCallbacks
    def test_login_error(self):
        """Login and error."""
        FakedSSOService.error_dict = {'failure': 'really'}

        e = yield self.assertFailure(self.client.login(),
                                     CredentialsError)
        self.assertEqual(e[0], FakedSSOService.error_dict)
