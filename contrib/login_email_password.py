# -*- coding: utf-8 -*-
#
# Copyright 2011-2013 Canonical Ltd.
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
"""Script that shows the qt gui."""

import sys

if sys.platform != 'win32':
    from twisted.internet import gireactor
    gireactor.install()

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from ubuntuone.platform.credentials import CredentialsManagementTool


@inlineCallbacks
def main(email='whomever@canonical.com', password='whatever'):
    """Perform a client request to be logged in."""
    credtool = CredentialsManagementTool()
    print 'Trying to get credentials for email:', email
    try:
        creds = yield credtool.login_email_password(email=email,
                                                    password=password)
        print "creds found!", creds
    except Exception, e:
        print "creds error!", e
    reactor.stop()


if __name__ == '__main__':
    print 'Enter email:'
    email = raw_input()
    print 'Enter password:'
    password = raw_input()
    main(email=email, password=password)
    reactor.run()
