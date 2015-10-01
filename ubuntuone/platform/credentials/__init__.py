# -*- coding: utf-8 -*-
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

"""Common code for the credentials management."""

import gettext
import logging
import os
import platform
import urllib
import sys

from functools import partial

from twisted.internet import defer

from ubuntu_sso import UI_EXECUTABLE_QT
from ubuntu_sso.credentials import (
    PING_URL_KEY,
    POLICY_URL_KEY,
    UI_EXECUTABLE_KEY,
    TC_URL_KEY,
)

from ubuntuone import clientdefs
from ubuntuone.logger import (
    basic_formatter,
    CustomRotatingFileHandler,
    log_call,
)
from ubuntuone.platform.logger import ubuntuone_log_dir

LOG_LEVEL = logging.DEBUG
path = os.path.join(ubuntuone_log_dir, 'credentials.log')
MAIN_HANDLER = CustomRotatingFileHandler(path)
MAIN_HANDLER.setFormatter(basic_formatter)
MAIN_HANDLER.setLevel(LOG_LEVEL)

logger = logging.getLogger("ubuntuone.credentials")
logger.setLevel(LOG_LEVEL)
logger.addHandler(MAIN_HANDLER)

NO_OP = lambda *args, **kwargs: None
Q_ = lambda string: gettext.dgettext(clientdefs.GETTEXT_PACKAGE, string)
APP_NAME = u"Magicicada"
TC_URL = u"https://one.ubuntu.com/terms/"
POLICY_URL = u"https://one.ubuntu.com/privacy/"


def platform_data():
    result = {'platform': platform.system(),
              'platform_version': platform.release(),
              'platform_arch': platform.machine(),
              'client_version': clientdefs.VERSION}
    # urlencode will not encode unicode, only bytes
    result = urllib.urlencode(result)
    return result


BASE_PING_URL = \
    u"https://one.ubuntu.com/oauth/sso-finished-so-get-tokens/{email}"
# the result of platform_data is given by urlencode, encoded with ascii
PING_URL = BASE_PING_URL + u"?" + platform_data().decode('ascii')
UI_PARAMS = {
    PING_URL_KEY: PING_URL,
    POLICY_URL_KEY: POLICY_URL,
    TC_URL_KEY: TC_URL,
    UI_EXECUTABLE_KEY: UI_EXECUTABLE_QT,
}


class CredentialsError(Exception):
    """A general exception when hadling credentilas."""


class CredentialsManagementTool(object):
    """Wrapper to CredentialsManagement.

    The goal of this class is to abstract the caller from calling the IPC
    service implemented in the class CredentialsManagement.

    """

    def __init__(self):
        self._cleanup_signals = []
        self._proxy = None

    def callback(self, result, deferred):
        """Fire 'deferred' with success, sending 'result' as result."""
        deferred.callback(result)

    def errback(self, error, deferred):
        """Fire 'deferred' with error sending a CredentialsError."""
        deferred.errback(CredentialsError(error))

    def cleanup(self, _):
        """Disconnect all the DBus signals."""
        for sig in self._cleanup_signals:
            logger.debug('cleanup: removing signal match %r', sig)
            remove = getattr(sig, "remove", None)
            if remove:
                remove()

        return _

    def get_platform_source(self):
        """Platform-specific source."""
        if sys.platform in ('win32', 'darwin'):
            from ubuntuone.platform.credentials import ipc_service
            source = ipc_service
        else:
            from ubuntuone.platform.credentials import dbus_service
            source = dbus_service
        return source

    @defer.inlineCallbacks
    def get_creds_proxy(self):
        """Call the platform-dependent get_creds_proxy caching the result."""
        if self._proxy is None:
            source = self.get_platform_source()
            self._proxy = yield source.get_creds_proxy()
        defer.returnValue(self._proxy)

    # do not log returned credentials
    @log_call(logger.debug, with_result=False)
    @defer.inlineCallbacks
    def find_credentials(self):
        """Find credentials for Magicicada.

        Return a deferred that, when fired, will return the credentials for
        Magicicada for the current logged in user.

        The credentials is a dictionary with both string keys and values. The
        dictionary may be either empty if there are no credentials for the
        user, or will hold five items as follow:

        - "name"
        - "token"
        - "token_secret"
        - "consumer_key"
        - "consumer_secret"

        """
        d = defer.Deferred()
        d.addBoth(self.cleanup)

        proxy = yield self.get_creds_proxy()

        sig = proxy.connect_to_signal('CredentialsFound', d.callback)
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'CredentialsNotFound',
            partial(self.callback, result={}, deferred=d))
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'CredentialsError', partial(self.errback, deferred=d))
        self._cleanup_signals.append(sig)

        done = defer.Deferred()
        proxy.find_credentials(
            reply_handler=partial(self.callback, result=None, deferred=done),
            error_handler=partial(self.errback, deferred=done))

        yield done

        result = yield d
        defer.returnValue(result)

    @log_call(logger.debug)
    @defer.inlineCallbacks
    def clear_credentials(self):
        """Clear credentials for Magicicada.

        Return a deferred that, when fired, will return no result but will
        indicate that the Magicicada credentials for the current user were
        removed from the local keyring.

        """
        d = defer.Deferred()
        d.addBoth(self.cleanup)

        proxy = yield self.get_creds_proxy()

        sig = proxy.connect_to_signal(
            'CredentialsCleared',
            partial(self.callback, result=None, deferred=d))
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'CredentialsError', partial(self.errback, deferred=d))
        self._cleanup_signals.append(sig)

        done = defer.Deferred()
        proxy.clear_credentials(
            reply_handler=partial(self.callback, result=None, deferred=done),
            error_handler=partial(self.errback, deferred=done))

        yield done

        yield d

    # do not log token
    @log_call(logger.debug, with_args=False)
    @defer.inlineCallbacks
    def store_credentials(self, token):
        """Store credentials for Magicicada.

        The parameter 'token' should be a dictionary that matches the
        description of the result of 'find_credentials'.

        Return a deferred that, when fired, will return no result but will
        indicate that 'token' was stored in the local keyring as the new Ubuntu
        One credentials for the current user.

        """
        d = defer.Deferred()
        d.addBoth(self.cleanup)

        proxy = yield self.get_creds_proxy()

        sig = proxy.connect_to_signal(
            'CredentialsStored',
            partial(self.callback, result=None, deferred=d))
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'CredentialsError', partial(self.errback, deferred=d))
        self._cleanup_signals.append(sig)

        done = defer.Deferred()
        proxy.store_credentials(
            token,
            reply_handler=partial(self.callback, result=None, deferred=done),
            error_handler=partial(self.errback, deferred=done))

        yield done

        yield d

    # do not log returned credentials
    @log_call(logger.debug, with_result=False)
    @defer.inlineCallbacks
    def register(self, window_id=0):
        """Register to Magicicada.

        Return a deferred that, when fired, will return the credentials for
        Magicicada for the current logged in user.

        If there are no credentials for the current user, a GTK UI will be
        opened to invite the user to register to Magicicada. This UI provides
        options to either register (main screen) or login (secondary screen).

        You can pass an optional 'window_id' parameter that will be used by the
        GTK UI to be set transient for it.

        The returned credentials will be either a non-empty dictionary like the
        one described in 'find_credentials', or None. The latter indicates that
        there were no credentials for the user in the local keyring and that
        the user refused to register to Magicicada.

        """
        d = defer.Deferred()
        d.addBoth(self.cleanup)

        proxy = yield self.get_creds_proxy()

        sig = proxy.connect_to_signal('CredentialsFound', d.callback)
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'AuthorizationDenied',
            partial(self.callback, result=None, deferred=d))
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'CredentialsError', partial(self.errback, deferred=d))
        self._cleanup_signals.append(sig)

        done = defer.Deferred()
        proxy.register(
            {'window_id': str(window_id)},
            reply_handler=partial(self.callback, result=None, deferred=done),
            error_handler=partial(self.errback, deferred=done))

        yield done

        result = yield d
        defer.returnValue(result)

    # do not log returned credentials
    @log_call(logger.debug, with_result=False)
    @defer.inlineCallbacks
    def login(self, window_id=0):
        """Login to Magicicada.

        Return a deferred that, when fired, will return the credentials for
        Magicicada for the current logged in user.

        If there are no credentials for the current user, a GTK UI will be
        opened to invite the user to login to Magicicada. This UI provides
        options to either login (main screen) or retrieve password (secondary
        screen).

        You can pass an optional 'window_id' parameter that will be used by the
        GTK UI to be set transient for it.

        The returned credentials will be either a non-empty dictionary like the
        one described in 'find_credentials', or None. The latter indicates that
        there were no credentials for the user in the local keyring and that
        the user refused to login to Magicicada.

        """
        d = defer.Deferred()
        d.addBoth(self.cleanup)

        proxy = yield self.get_creds_proxy()

        sig = proxy.connect_to_signal('CredentialsFound', d.callback)
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'AuthorizationDenied',
            partial(self.callback, result=None, deferred=d))
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'CredentialsError', partial(self.errback, deferred=d))
        self._cleanup_signals.append(sig)

        done = defer.Deferred()
        proxy.login(
            {'window_id': str(window_id)},
            reply_handler=partial(self.callback, result=None, deferred=done),
            error_handler=partial(self.errback, deferred=done))

        yield done

        result = yield d
        defer.returnValue(result)

    # do not log password nor returned credentials
    @log_call(logger.debug, with_args=False, with_result=False)
    @defer.inlineCallbacks
    def login_email_password(self, email, password):
        """Login to Magicicada.

        Return a deferred that, when fired, will return the credentials for
        Magicicada for the given email and password.

        The returned credentials will be either a non-empty dictionary like the
        one described in 'find_credentials', or None. The latter indicates
        invalid or wrong user/password.

        """
        d = defer.Deferred()
        d.addBoth(self.cleanup)

        proxy = yield self.get_creds_proxy()

        sig = proxy.connect_to_signal('CredentialsFound', d.callback)
        self._cleanup_signals.append(sig)

        sig = proxy.connect_to_signal(
            'CredentialsError', partial(self.errback, deferred=d))
        self._cleanup_signals.append(sig)

        done = defer.Deferred()
        proxy.login_email_password(
            {'email': email, 'password': password},
            reply_handler=partial(self.callback, result=None, deferred=done),
            error_handler=partial(self.errback, deferred=done))

        yield done

        result = yield d
        defer.returnValue(result)
