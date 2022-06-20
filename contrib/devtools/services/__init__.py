# Copyright 2011-2012 Canonical Ltd.
# Copyright 2018 Chicharreros (https://launchpad.net/~chicharreros)
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
"""Service runners for testing."""

import os
import socket

from dirspec.basedir import load_data_paths


def find_config_file(in_config_file):
    """Find the first appropriate conf to use."""
    # In case we're running from within the source tree
    path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                        os.path.pardir, os.path.pardir,
                                        os.path.pardir,
                                        "data", in_config_file))
    if not os.path.exists(path):
        # Use the installed file in $pkgdatadir as source
        for path in load_data_paths(in_config_file):
            if os.path.exists(path):
                break

    # Check to make sure we didn't just fall out of the loop
    if not os.path.exists(path):
        raise IOError('Could not locate suitable %s' % in_config_file)
    return path


def get_arbitrary_port():
    """
    Find an unused port, and return it.

    There might be a small race condition here, but we aren't
    worried about it.
    """
    sock = socket.socket()
    sock.bind(('localhost', 0))
    _, port = sock.getsockname()
    sock.close()
    return port
