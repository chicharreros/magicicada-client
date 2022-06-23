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
"""Tests for Tritcask and helper functions."""

import os
import uuid

from tritcask import Tritcask as UpstreamTritcask

from magicicadaclient.testing.testcase import BaseTwistedTestCase
from magicicadaclient.syncdaemon.tritcask import Tritcask, TritcaskShelf


class TritcaskTestCase(BaseTwistedTestCase):
    """Testcase for Tritcask."""

    def make_db(self):
        base_dir = self.mktemp('data_dir')
        db = Tritcask(base_dir)
        self.addCleanup(db.shutdown)
        return db

    def test_inheritance(self):
        """Basic test for the put method."""
        db = self.make_db()
        self.assertIsInstance(db, UpstreamTritcask)

    def test_put_str(self):
        """Basic test for the put method when key is a str."""
        db = self.make_db()
        key = str(uuid.uuid4())
        data = os.urandom(50)

        db.put(0, key, data)

        self.assertEqual([(0, key.encode('utf-8'))], list(db._keydir.keys()))
        self.assertEqual([(0, key)], list(db.keys()))
        self.assertEqual(db.get(0, key), data)

    def test_put_bytes(self):
        """Basic test for the put method when key is bytes."""
        db = self.make_db()
        key = 'I ♡ unicode'
        key_bytes = key.encode('utf-8')
        data = os.urandom(50)
        db.put(0, key, data)

        self.assertEqual([(0, key_bytes)], list(db._keydir.keys()))
        self.assertEqual([(0, key)], list(db.keys()))
        self.assertEqual(db.get(0, key), data)

    def test_get_str(self):
        """Basic test for the get method when key is a str."""
        db = self.make_db()
        key = str(uuid.uuid4())
        data = os.urandom(50)
        db.put(0, key, data)

        self.assertEqual([(0, key.encode('utf-8'))], list(db._keydir.keys()))
        self.assertEqual([(0, key)], list(db.keys()))
        self.assertEqual(db.get(0, key), data)

    def test_get_bytes(self):
        """Basic test for the get method when key is bytes."""
        db = self.make_db()
        key = 'I ♡ unicode'
        key_bytes = key.encode('utf-8')
        data = os.urandom(50)
        db.put(0, key, data)

        self.assertEqual([(0, key_bytes)], list(db._keydir.keys()))
        self.assertEqual([(0, key)], list(db.keys()))
        self.assertEqual(db.get(0, key), data)

    def test_delete_str(self):
        """Basic test for the get method when key is a str."""
        db = self.make_db()
        key = str(uuid.uuid4())
        data = os.urandom(50)
        db.put(0, key, data)

        db.delete(0, key)

        self.assertEqual([], list(db._keydir.keys()))
        self.assertEqual([], list(db.keys()))
        self.assertRaises(KeyError, db.get, 0, key)

    def test_delete_bytes(self):
        """Basic test for the get method when key is bytes."""
        db = self.make_db()
        key = 'I ♡ unicode'
        data = os.urandom(50)
        db.put(0, key, data)

        db.delete(0, key)

        self.assertEqual([], list(db._keydir.keys()))
        self.assertEqual([], list(db.keys()))
        self.assertRaises(KeyError, db.get, 0, key)

    def test_keys(self):
        """Test for the keys() method."""
        db = self.make_db()
        keys = []
        for i in range(3):
            k = 'I ♡ %s' % i
            keys.append(k)
            db.put(0, k, os.urandom(50))

        self.assertEqual([(0, k) for k in keys], list(db.keys()))
        self.assertEqual(
            list(db._keydir.keys()), [(0, k.encode('utf-8')) for k in keys])

    def test__contains__(self):
        """Test for __contains__ method."""
        db = self.make_db()
        keys = []
        for i in range(3):
            k = 'I ♡ %s' % i
            keys.append(k)
            db.put(0, k, os.urandom(50))

        for k in keys:
            with self.subTest(key=k):
                self.assertIn((0, k), db)
                self.assertIn((0, k.encode('utf-8')), db._keydir)

        self.assertNotIn((0, 'I ♡ 3'), db)


class TritcaskShelfTestCase(BaseTwistedTestCase):

    def test_deserialize_os_stat(self):
        # "Remove import copyreg from os module"
        # https://bugs.python.org/issue19209
        # Python 2's pickle including a stat result produce the following
        # error in Python 3, since the `copyreg` section (?) was removed:
        # builtins.AttributeError: Can't get attribute '_make_stat_result' on
        # <module 'os' from '/usr/lib/python3.8/os.py'>

        os_stat_pickle = (  # the Python 2 cPickle of `os.stat('.')`
            b"cos\n_make_stat_result\np1\n((I16893\nI1705881\nI64769\nI3\nI100"
            b"0\nI1000\nI4096\nI1655922497\nI1655922488\nI1655922488\nt(dp2\n"
            b"S'st_ctime'\np3\nF1655922488.2818279\nsS'st_rdev'\np4\nI0\nsS'"
            b"st_mtime'\np5\nF1655922488.2818279\nsS'st_blocks'\np6\nI8\nsS'"
            b"st_atime'\np7\nF1655922497.6138899\nsS'st_blksize'\np8\nI4096\n"
            b"stRp9\n."
        )

        result = TritcaskShelf(row_type=1, db={})._deserialize(os_stat_pickle)
        self.assertIsInstance(result, os.stat_result)
