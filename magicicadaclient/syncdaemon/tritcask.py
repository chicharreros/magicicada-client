# Copyright 2022 Chicharreros (https://launchpad.net/~chicharreros)
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

"""Bitcask-like (row_type,key)/value store.

Abstraction layer on top of tritcask's upstream to handle str instead of bytes.

"""

import tritcask


TritcaskShelf = tritcask.TritcaskShelf


class Tritcask(tritcask.Tritcask):
    """Abstraction layer on top of tritcask.Tritcask."""

    def __contains__(self, key):
        """Return True if key is in self._keydir."""
        row_type, k = key
        if not isinstance(k, str):
            raise ValueError('key must be a str (got %r).' % k)
        return (row_type, k.encode('utf-8')) in self._keydir

    def keys(self):
        """Return the keys in self._keydir."""
        return ((t, k.decode('utf-8')) for (t, k) in list(self._keydir.keys()))

    def put(self, row_type, key, value):
        """Put key/value in the store."""
        if isinstance(key, str):
            key = key.encode('utf-8')
        super().put(row_type, key, value)

    def get(self, row_type, key):
        """Get the value for the specified row_type, key."""
        if isinstance(key, str):
            key = key.encode('utf-8')
        return super().get(row_type, key)

    def delete(self, row_type, key):
        """Delete the key/value specified by key."""
        if isinstance(key, str):
            key = key.encode('utf-8')
        super().delete(row_type, key)
