# Copyright 2010-2013 Canonical Ltd.
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

"""Linux specific tests for the platform module."""

import os

from magicicadaclient.platform import move_to_trash, open_file, stat_path
from magicicadaclient.platform.tests.os_helper import test_os_helper
from magicicadaclient.platform.os_helper import linux


class OSWrapperTests(test_os_helper.OSWrapperTests):
    """Tests for os wrapper functions."""

    def test_stat_symlink(self):
        """Test that it doesn't follow symlinks.

        We compare the inode only (enough to see if it's returning info
        from the link or the linked), as we can not compare the full stat
        because the st_mode will be different.
        """
        link = os.path.join(self.basedir, 'foo')
        os.symlink(self.testfile, link)
        self.assertNotEqual(os.stat(link).st_ino, stat_path(link).st_ino)
        self.assertEqual(os.lstat(link).st_ino, stat_path(link).st_ino)

    def test_movetotrash_bad(self):
        """Something bad happen when moving to trash, removed anyway.

        Simulating this as giving a non-existant path to the function, which
        will make it fail with OSError, which is the exception the send2trash
        library raises on any problem.
        """
        called = []
        self.patch(linux, '_remove_path', lambda p: called.append(p))

        path = os.path.join(self.basedir, 'non-existant')
        move_to_trash(path)
        self.assertEqual(called[0], path)
        self.assertTrue(
            self.handler.check_warning(
                "Problems moving to trash!", "Removing anyway", path
            )
        )

    def test_remove_path_file(self):
        path = os.path.join(self.basedir, 'foo')
        open_file(path, 'w').close()
        linux._remove_path(path)
        self.assertFalse(os.path.exists(path))

    def test_remove_path_dir(self):
        path = os.path.join(self.basedir, 'foo')
        os.mkdir(path)
        open_file(os.path.join(path, 'file inside directory'), 'w').close()
        linux._remove_path(path)
        self.assertFalse(os.path.exists(path))
