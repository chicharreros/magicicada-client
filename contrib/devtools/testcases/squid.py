# Copyright 2011-2012 Canonical Ltd.
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

"""Base squid tests cases and test utilities."""

from devtools.testcases import BaseTestCase, skipIf
from devtools.services.squid import (
    SquidRunner,
    SquidLaunchError,
    get_squid_executable,
    get_htpasswd_executable,
    retrieve_proxy_settings)

squid, _ = get_squid_executable()
htpasswd = get_htpasswd_executable()


@skipIf(squid is None or htpasswd is None,
        'The test requires squid and htpasswd.')
class SquidTestCase(BaseTestCase):
    """Test that uses a proxy."""

    def required_services(self):
        """Return the list of required services for DBusTestCase."""
        services = super(SquidTestCase, self).required_services()
        services.extend([SquidRunner])
        return services

    def get_nonauth_proxy_settings(self):
        """Return the settings of the noneauth proxy."""
        settings = retrieve_proxy_settings()
        if settings is None:
            raise SquidLaunchError('Proxy is not running.')
        return dict(host='localhost', port=settings['noauth_port'])

    def get_auth_proxy_settings(self):
        """Return the settings of the auth proxy."""
        settings = retrieve_proxy_settings()
        if settings is None:
            raise SquidLaunchError('Proxy is not running.')
        return dict(host='localhost', port=settings['auth_port'],
                    username=settings['username'],
                    password=settings['password'])
