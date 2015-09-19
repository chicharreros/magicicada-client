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
"""Magicicada credentials management dbus service."""

import dbus
import dbus.service
import ubuntu_sso

from ubuntuone.platform.credentials import (
    APP_NAME,
    logger,
    NO_OP,
    UI_PARAMS,
)


TIMEOUT_INTERVAL = 10000  # 10 seconds

# constants
DBUS_BUS_NAME = "com.ubuntuone.Credentials"
DBUS_CREDENTIALS_PATH = "/credentials"
DBUS_CREDENTIALS_IFACE = "com.ubuntuone.CredentialsManagement"


class CredentialsManagement(dbus.service.Object):
    """DBus object that manages Magicicada credentials."""

    def __init__(self, timeout_func=lambda *a: None,
                 shutdown_func=lambda *a: None, *args, **kwargs):
        super(CredentialsManagement, self).__init__(*args, **kwargs)
        self._ref_count = 0
        self.timeout_func = timeout_func
        self.shutdown_func = shutdown_func

        self.sso_match = None
        self.sso_proxy = self._get_sso_proxy()

    def _signal_handler(self, *args, **kwargs):
        """Generic signal handler."""
        member = kwargs.get('member', None)
        app_name = args[0] if len(args) > 0 else None
        logger.debug('Handling DBus signal for member: %r, app_name: %r.',
                     member, app_name)

        if app_name != APP_NAME:
            logger.info('Received %r but app_name %r does not match %r, '
                        'exiting.', member, app_name, APP_NAME)
            return

        sig = getattr(self, member)

        if member in ('CredentialsFound', 'CredentialsError'):
            # this are the only signals that will forward the parameter
            logger.info('%r', member)
            arg = args[1]
            sig(arg)
        else:
            sig()

    def _get_sso_proxy(self):
        """Get the SSO dbus proxy."""
        bus = dbus.SessionBus()
        # register signal handlers for each kind of error
        self.sso_match = bus.add_signal_receiver(
            self._signal_handler, member_keyword='member',
            dbus_interface=ubuntu_sso.DBUS_CREDENTIALS_IFACE)
        try:
            obj = bus.get_object(ubuntu_sso.DBUS_BUS_NAME,
                                 ubuntu_sso.DBUS_CREDENTIALS_PATH,
                                 follow_name_owner_changes=True)
            proxy = dbus.Interface(obj, ubuntu_sso.DBUS_CREDENTIALS_IFACE)
        except:
            logger.exception('get_sso_proxy:')
            raise

        return proxy

    def _get_ref_count(self):
        """Get value of ref_count."""
        return self._ref_count

    def _set_ref_count(self, new_value):
        """Set a new value to ref_count."""
        logger.debug('ref_count is %r, changing value to %r.',
                     self._ref_count, new_value)
        if new_value < 0:
            self._ref_count = 0
            msg = 'Attempting to decrease ref_count to a negative value (%r).'
            logger.warning(msg, new_value)
        else:
            self._ref_count = new_value

        if self._ref_count == 0:
            logger.debug('Setting up timer with %r (%r, %r).',
                         self.timeout_func, TIMEOUT_INTERVAL, self.shutdown)
            self.timeout_func(TIMEOUT_INTERVAL, self.shutdown)

    ref_count = property(fget=_get_ref_count, fset=_set_ref_count)

    def shutdown(self):
        """If no ongoing requests, call self.shutdown_func."""
        logger.debug('shutdown!, ref_count is %r.', self._ref_count)
        if self._ref_count == 0:
            logger.info('Shutting down, calling %r.', self.shutdown_func)
            self.shutdown_func()

    # Operator not preceded by a space (fails with dbus decorators)

    @dbus.service.signal(DBUS_CREDENTIALS_IFACE)
    def AuthorizationDenied(self):
        """Signal thrown when the user denies the authorization."""
        self.ref_count -= 1
        logger.info('%s: emitting AuthorizationDenied.',
                    self.__class__.__name__)

    @dbus.service.signal(DBUS_CREDENTIALS_IFACE, signature='a{ss}')
    def CredentialsFound(self, credentials):
        """Signal thrown when the credentials are found."""
        self.ref_count -= 1
        logger.info('%s: emitting CredentialsFound.',
                    self.__class__.__name__)

    @dbus.service.signal(DBUS_CREDENTIALS_IFACE)
    def CredentialsNotFound(self):
        """Signal thrown when the credentials are not found."""
        self.ref_count -= 1
        logger.info('%s: emitting CredentialsNotFound.',
                    self.__class__.__name__)

    @dbus.service.signal(DBUS_CREDENTIALS_IFACE)
    def CredentialsCleared(self):
        """Signal thrown when the credentials were cleared."""
        self.ref_count -= 1
        logger.info('%s: emitting CredentialsCleared.',
                    self.__class__.__name__)

    @dbus.service.signal(DBUS_CREDENTIALS_IFACE)
    def CredentialsStored(self):
        """Signal thrown when the credentials were cleared."""
        self.ref_count -= 1
        logger.info('%s: emitting CredentialsStored.',
                    self.__class__.__name__)

    @dbus.service.signal(DBUS_CREDENTIALS_IFACE, signature='a{ss}')
    def CredentialsError(self, error_dict):
        """Signal thrown when there is a problem getting the credentials."""
        self.ref_count -= 1
        logger.error('%s: emitting CredentialsError with error_dict %r.',
                     self.__class__.__name__, error_dict)

    @dbus.service.method(dbus_interface=DBUS_CREDENTIALS_IFACE,
                         async_callbacks=("reply_handler", "error_handler"))
    def find_credentials(self, reply_handler=NO_OP, error_handler=NO_OP):
        """Ask the Magicicada credentials."""
        self.ref_count += 1
        self.sso_proxy.find_credentials(
            APP_NAME, dbus.Dictionary({}, signature='ss'),
            reply_handler=reply_handler, error_handler=error_handler)

    @dbus.service.method(dbus_interface=DBUS_CREDENTIALS_IFACE,
                         out_signature="a{ss}",
                         async_callbacks=("reply_handler", "error_handler"))
    def find_credentials_sync(self, reply_handler=NO_OP, error_handler=NO_OP):
        """Ask the Magicicada credentials synchronously.

        This method SHOULD NOT be used, is here only for compatibilty issues.

        """

        def decrease_counter_success(credentials):
            """Call 'callback' and decrease the root ref counter."""
            reply_handler(credentials)
            self.ref_count -= 1

        def decrease_counter_error(error):
            """Call 'errback' and decrease the root ref counter."""
            error_handler(error)
            self.ref_count -= 1

        self.ref_count += 1
        self.sso_proxy.find_credentials_sync(
            APP_NAME,
            dbus.Dictionary({}, signature='ss'),
            reply_handler=decrease_counter_success,
            error_handler=decrease_counter_error)

    @dbus.service.method(dbus_interface=DBUS_CREDENTIALS_IFACE,
                         async_callbacks=("reply_handler", "error_handler"))
    def clear_credentials(self, reply_handler=NO_OP, error_handler=NO_OP):
        """Clear the Magicicada credentials."""
        self.ref_count += 1
        self.sso_proxy.clear_credentials(
            APP_NAME, dbus.Dictionary({}, signature='ss'),
            reply_handler=reply_handler, error_handler=error_handler)

    @dbus.service.method(dbus_interface=DBUS_CREDENTIALS_IFACE,
                         in_signature='a{ss}',
                         async_callbacks=("reply_handler", "error_handler"))
    def store_credentials(self, credentials,
                          reply_handler=NO_OP, error_handler=NO_OP):
        """Store the token for Magicicada application."""
        self.ref_count += 1
        self.sso_proxy.store_credentials(
            APP_NAME, credentials,
            reply_handler=reply_handler, error_handler=error_handler)

    @dbus.service.method(dbus_interface=DBUS_CREDENTIALS_IFACE,
                         in_signature='a{ss}',
                         async_callbacks=("reply_handler", "error_handler"))
    def register(self, args, reply_handler=NO_OP, error_handler=NO_OP):
        """Get credentials if found else prompt to register to Magicicada."""
        self.ref_count += 1
        params = dict(UI_PARAMS)
        params.update(args)
        self.sso_proxy.register(
            APP_NAME, params,
            reply_handler=reply_handler, error_handler=error_handler)

    @dbus.service.method(dbus_interface=DBUS_CREDENTIALS_IFACE,
                         in_signature='a{ss}',
                         async_callbacks=("reply_handler", "error_handler"))
    def login(self, args, reply_handler=NO_OP, error_handler=NO_OP):
        """Get credentials if found else prompt to login to Magicicada."""
        self.ref_count += 1
        params = dict(UI_PARAMS)
        params.update(args)
        self.sso_proxy.login(
            APP_NAME, params,
            reply_handler=reply_handler, error_handler=error_handler)

    @dbus.service.method(dbus_interface=DBUS_CREDENTIALS_IFACE,
                         in_signature='a{ss}',
                         async_callbacks=("reply_handler", "error_handler"))
    def login_email_password(self, args, reply_handler=NO_OP,
                             error_handler=NO_OP):
        """Get credentials if found else prompt to login to Magicicada."""
        self.ref_count += 1
        params = dict(UI_PARAMS)
        params.update(args)
        self.sso_proxy.login_email_password(
            APP_NAME, params,
            reply_handler=reply_handler, error_handler=error_handler)


def get_creds_proxy():
    """Get the CredentialsManagement proxy."""
    bus = dbus.SessionBus()
    try:
        obj = bus.get_object(DBUS_BUS_NAME,
                             DBUS_CREDENTIALS_PATH,
                             follow_name_owner_changes=True)
        proxy = dbus.Interface(obj, DBUS_CREDENTIALS_IFACE)
    except:
        logger.exception('get_creds_proxy:')
        raise

    return proxy
