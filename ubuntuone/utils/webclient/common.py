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

"""The common bits of a webclient."""

import collections
import logging

from httplib2 import iri2uri
from twisted.internet import defer

from ubuntuone.utils.webclient.timestamp import TimestampChecker


logger = logging.getLogger(__name__)


class WebClientError(Exception):
    """An http error happened while calling the webservice."""


class UnauthorizedError(WebClientError):
    """The request ended with bad_request, unauthorized or forbidden."""


class ProxyUnauthorizedError(WebClientError):
    """Failure raised when there is an issue with the proxy auth."""


class Response(object):
    """A response object."""

    def __init__(self, content, headers=None):
        """Initialize this instance."""
        self.content = content
        self.headers = headers


class HeaderDict(collections.defaultdict):
    """A case insensitive dict for headers."""

    def __init__(self, *args, **kwargs):
        """Handle case-insensitive keys."""
        super(HeaderDict, self).__init__(list, *args, **kwargs)
        for key, value in self.items():
            super(HeaderDict, self).__delitem__(key)
            self[key] = value

    def __setitem__(self, key, value):
        """Set the value with a case-insensitive key."""
        super(HeaderDict, self).__setitem__(key.lower(), value)

    def __getitem__(self, key):
        """Get the value with a case-insensitive key."""
        return super(HeaderDict, self).__getitem__(key.lower())

    def __delitem__(self, key):
        """Delete the item with the case-insensitive key."""
        super(HeaderDict, self).__delitem__(key.lower())

    def __contains__(self, key):
        """Check the containment with a case-insensitive key."""
        return super(HeaderDict, self).__contains__(key.lower())


class BaseWebClient(object):
    """The webclient base class, to be extended by backends."""

    timestamp_checker = None

    def __init__(self, appname='', username=None, password=None):
        """Initialize this instance."""
        self.appname = appname
        self.username = username
        self.password = password
        self.proxy_username = None
        self.proxy_password = None

    def request(self, iri, method="GET", extra_headers=None,
                post_content=None):
        """Return a deferred that will be fired with a Response object."""
        raise NotImplementedError

    @classmethod
    def get_timestamp_checker(cls):
        """Get the timestamp checker for this class of webclient."""
        if cls.timestamp_checker is None:
            cls.timestamp_checker = TimestampChecker(cls)
        return cls.timestamp_checker

    def get_timestamp(self):
        """Get a timestamp synchronized with the server."""
        return self.get_timestamp_checker().get_faithful_time()

    def force_use_proxy(self, settings):
        """Setup this webclient to use the given proxy settings."""
        raise NotImplementedError

    def iri_to_uri(self, iri):
        """Transform a unicode iri into a ascii uri."""
        if not isinstance(iri, unicode):
            raise TypeError('iri %r should be unicode.' % iri)
        return bytes(iri2uri(iri))

    def build_auth_request(self, method, uri, credentials, timestamp):
        """Build an auth request given some credentials."""
        # XXX: implement
        return {'Authorization': 'Auth dummy'}

    @defer.inlineCallbacks
    def build_request_headers(self, uri, method="GET", extra_headers=None,
                              auth_credentials=None):
        """Build the headers for a request."""
        if extra_headers:
            headers = dict(extra_headers)
        else:
            headers = {}

        if auth_credentials:
            timestamp = yield self.get_timestamp()
            signed_headers = self.build_auth_request(
                method, uri, auth_credentials, timestamp)
            headers.update(signed_headers)

        defer.returnValue(headers)

    @defer.inlineCallbacks
    def build_signed_iri(self, iri, credentials, parameters=None):
        """Build a new iri signing 'iri' with 'credentials'."""
        uri = self.iri_to_uri(iri)
        timestamp = yield self.get_timestamp()
        url = self.build_auth_request(
            method='GET', uri=uri, credentials=credentials,
            timestamp=timestamp)
        defer.returnValue(url)

    def shutdown(self):
        """Shut down all pending requests (if possible)."""

    @defer.inlineCallbacks
    def _load_proxy_creds_from_keyring(self, domain):
        """Load the proxy creds from the keyring."""
        from ubuntuone.keyring import Keyring
        keyring = Keyring()
        try:
            creds = yield keyring.get_credentials(str(domain))
            logger.debug('Got credentials from keyring.')
        except Exception as e:
            logger.error('Error when retrieving the creds.')
            raise WebClientError('Error when retrieving the creds.', e)
        if creds is not None:
            # if we are loading the same creds it means that we got the wrong
            # ones
            if (self.proxy_username == creds['username'] and
                    self.proxy_password == creds['password']):
                defer.returnValue(False)
            else:
                self.proxy_username = creds['username']
                self.proxy_password = creds['password']
                defer.returnValue(True)
        logger.debug('Proxy creds not in keyring.')
        defer.returnValue(False)
