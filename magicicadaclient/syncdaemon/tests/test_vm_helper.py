# Copyright 2010-2012 Canonical Ltd.
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

"""Test for the VolumeManager helper."""

import os
import uuid

from magicicadaclient.testing.testcase import BaseTwistedTestCase
from magicicadaclient.platform import expand_user, os_helper
from magicicadaclient.syncdaemon import vm_helper
from magicicadaclient.syncdaemon.tests.test_vm import BaseVolumeManagerTests
from magicicadaclient.syncdaemon.vm_helper import (
    create_shares_link,
    get_share_dir_name,
    get_udf_path,
    get_udf_suggested_path,
)


class VMHelperTest(BaseVolumeManagerTests):
    """Test the vm_helper methods."""

    def _test_get_udf_path(self, suggested_path):
        """Assert that the resulting udf path is correct."""
        assert isinstance(suggested_path, str)
        assert suggested_path.startswith('~')

        path = get_udf_path(suggested_path)
        expected = suggested_path.replace('/', os.path.sep)
        expected = expand_user(expected)
        self.assertEqual(path, expected)

    def test_get_udf_path(self):
        """A bytes sequence is returned."""
        self._test_get_udf_path(suggested_path='~/Documents')

    def test_get_udf_path_non_ascii(self):
        """A bytes sequence is returned."""
        self._test_get_udf_path(suggested_path='~/Documents/Ñoño ñandú')

    def test_get_udf_path_funny_chars(self):
        """A bytes sequence is returned."""
        self._test_get_udf_path(suggested_path='~/Documents/Nr 1: really?')

    def test_get_udf_suggested_path(self):
        """Test for get_udf_suggested_path."""
        in_home = os.path.join(self.home_dir, 'foo')
        self.assertEqual('~/foo', get_udf_suggested_path(in_home))

    def test_get_udf_suggested_path_expand_user(self):
        """Test for get_udf_suggested_path."""
        home = os.path.join(self.home_dir, '雄鳥お人好し ñandú')

        def fake_expand_user(path):
            """Fake expand_user."""
            return home

        self.patch(vm_helper, 'expand_user', fake_expand_user)
        in_home = os.path.join(home, 'ñoño')
        suggested_path = get_udf_suggested_path(in_home)
        self.assertEqual('~/ñoño', suggested_path)

    def test_get_udf_suggested_path_long_path(self):
        """Test for get_udf_suggested_path."""
        deep_in_home = os.path.join(self.home_dir, 'docs', 'foo', 'bar')
        actual = get_udf_suggested_path(deep_in_home)
        self.assertEqual('~/docs/foo/bar', actual)

    def test_get_udf_suggested_path_value_error(self):
        """Test for get_udf_suggested_path."""
        outside_home = os.path.join(
            self.home_dir, os.path.pardir, 'bar', 'foo'
        )
        relative_home = os.path.join(os.path.pardir, os.path.pardir, 'foo')
        self.assertRaises(ValueError, get_udf_suggested_path, outside_home)
        self.assertRaises(ValueError, get_udf_suggested_path, None)
        self.assertRaises(ValueError, get_udf_suggested_path, relative_home)


class VMHelperLinkTestCase(BaseTwistedTestCase):
    """Tests for the VM Helper symlinks."""

    def test_create_shares_link_exists(self):
        """create_shares_link is noop when there's something with that name."""
        base = self.mktemp("test_create_shares_link_exists")
        source_path = os.path.join(base, "source")
        dest_path = os.path.join(base, "dest")
        os_helper.make_dir(dest_path)
        self.assertFalse(create_shares_link(source_path, dest_path))

    def test_create_shares_link_existing_destiny_with_lnk_extension(self):
        """Add the lnk extension to the end of the file like windows needs."""
        base = self.mktemp("test_create_shares_link_exists")
        source_path = os.path.join(base, "source")
        dest_path = os.path.join(base, "dest.lnk")
        os_helper.make_dir(dest_path)
        self.assertFalse(create_shares_link(source_path, dest_path))

    def test_create_shares_link_makes_the_link(self):
        """create_shares_link makes the link as expected."""
        base = self.mktemp("test_create_shares_link_makes_the_link")
        source_path = os.path.join(base, "source")
        dest_path = os.path.join(base, "dest")
        os_helper.make_dir(source_path)
        self.assertTrue(create_shares_link(source_path, dest_path))
        self.assertTrue(vm_helper.is_link(dest_path))

    def test_create_shares_link_existing(self):
        """create_shares_link on an existing path does nothing."""
        base = self.mktemp("test_create_shares_link_makes_the_link")
        source_path = os.path.join(base, "source")
        dest_path = os.path.join(base, "dest")
        os_helper.make_dir(source_path)
        self.assertTrue(create_shares_link(source_path, dest_path))
        self.assertFalse(create_shares_link(source_path, dest_path))

    def test_create_shares_link_existing_source_with_lnk_extension(self):
        """Add the lnk extension to the end of the file like windows needs."""
        base = self.mktemp("test_create_shares_link_makes_the_link")
        source_path = os.path.join(base, "source")
        dest_path = os.path.join(base, "dest.lnk")
        os_helper.make_dir(source_path)
        self.assertTrue(create_shares_link(source_path, dest_path))
        self.assertFalse(create_shares_link(source_path, dest_path))


class GetShareDirNameTests(BaseVolumeManagerTests):
    share_id = uuid.uuid4()
    name = 'The little pretty share (♥)'

    def test_get_share_dir_name(self):
        """Test for get_share_dir_name."""
        other_name = 'Dorian Grey'
        share = self._create_share_volume(
            volume_id=self.share_id,
            name=self.name,
            other_visible_name=other_name,
        )
        result = get_share_dir_name(share)

        expected = '%s (%s, %s)' % (self.name, other_name, self.share_id)
        self.assertEqual(result, expected)

    def test_get_share_dir_name_visible_name_empty(self):
        """Test for get_share_dir_name."""
        other_name = ''
        share = self._create_share_volume(
            volume_id=self.share_id,
            name=self.name,
            other_visible_name=other_name,
        )
        result = get_share_dir_name(share)

        expected = '%s (%s)' % (self.name, self.share_id)
        self.assertEqual(result, expected)
