# Copyright 2009-2012 Canonical Ltd.
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

"""Tests the Hashs Queue."""

import inspect
import os
import unittest

from twisted.internet import defer, reactor

from magicicadaclient.testing.testcase import (
    BaseTwistedTestCase,
    FakeVolumeManager,
    skip_if_win32_missing_fs_event,
)
from magicicadaclient.syncdaemon import (
    filesystem_manager,
    event_queue,
    events_nanny,
    hash_queue,
    tritcask,
)


class EventListener:
    """Store the events."""

    def __init__(self):
        self._events = []

    def handle_default(self, event, **args):
        """Store the received event."""
        self._events.append((event,) + tuple(sorted(args.values())))

    def events(self):
        """Clean and return events."""
        tmp = self._events
        self._events = []
        return tmp


def hash_hack_run(self):
    """Function to hack the hash class to avoid it processing the requests."""
    while True:
        info, timestamp = self.queue.get()
        try:
            path, mdid = info
        except TypeError:
            break
        self.hashing = path


class DownloadFinishedTests(BaseTwistedTestCase):
    """Test the AQ Download Finished Nanny behaviour."""

    timeout = 2

    @defer.inlineCallbacks
    def setUp(self):
        """set up the test."""
        yield super(DownloadFinishedTests, self).setUp()
        self.usrdir = self.mktemp("usrdir")
        self.partials_dir = self.mktemp("partials")

        # hack hash queue
        self._original_hash_run = hash_queue._Hasher.run
        hash_queue._Hasher.run = hash_hack_run

        # create vm, fsm, eq, hq...
        vm = FakeVolumeManager(self.usrdir)
        db = tritcask.Tritcask(self.mktemp('tritcask'))
        self.addCleanup(db.shutdown)
        self.fsm = fsm = filesystem_manager.FileSystemManager(
            self.usrdir, self.partials_dir, vm, db
        )
        self.eq = eq = event_queue.EventQueue(fsm)
        self.addCleanup(eq.shutdown)
        self.hq = hq = hash_queue.HashQueue(eq)
        self.nanny = events_nanny.DownloadFinishedNanny(fsm, eq, hq)
        self.listener = EventListener()
        eq.subscribe(self.listener)

        # create the file
        self.tf = os.path.join(self.usrdir, "testfile")
        fsm.create(self.tf, "")
        fsm.set_node_id(self.tf, "nodeid")

    @defer.inlineCallbacks
    def tearDown(self):
        """tear down the test."""
        hash_queue._Hasher.run = self._original_hash_run
        self.hq.shutdown()
        yield super(DownloadFinishedTests, self).tearDown()

    def insert_in_hq(self, path, node_id):
        """Inserts something in HQ and waits that thread."""
        d = defer.Deferred()
        self.hq.insert(path, node_id)

        def wait():
            """waits for the var to get set"""
            if self.hq.hasher.hashing is None:
                reactor.callLater(0.1, wait)
            else:
                d.callback(None)

        reactor.callLater(0.1, wait)
        return d

    def release_hq(self):
        """Releases HQ as it finished."""
        d = defer.Deferred()
        self.hq.insert(None, None)

        def wait():
            """waits for the var to get set"""
            if self.hq.hasher.hashing is not None:
                reactor.callLater(0.1, wait)
            else:
                d.callback(None)

        reactor.callLater(0.1, wait)
        return d

    def test_forward(self):
        """Forwards the event when file is not blocked."""
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)

    def test_blocks_when_open(self):
        """Blocks the event if the file is opened."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)

    @defer.inlineCallbacks
    def test_blocks_when_hashing(self):
        """Blocks the event if the file is being hashed."""
        yield self.insert_in_hq(self.tf, "nodeid")
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )
        self.assertEqual(
            self.listener.events(),
            [("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash")],
        )
        self.assertIn(self.tf, self.nanny._blocked)

    def test_closenowrite(self):
        """A close_nowrite received, but no file was blocked."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)

        self.eq.push("FS_FILE_CLOSE_WRITE", path=self.tf)
        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_WRITE", self.tf)]
        )
        self.assertIn(self.tf, self.nanny._blocked)

    def test_blocks_closewrite(self):
        """Blocks the event and does NOT release it when close write."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[self.tf], 1)

        self.eq.push("FS_FILE_CLOSE_WRITE", path=self.tf)

        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_WRITE", self.tf)]
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._opened)

    def test_blocks_release_close(self):
        """Blocks the event and releases it when close."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[self.tf], 1)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=self.tf)
        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_CLOSE_NOWRITE", self.tf),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._opened)

    def test_blocks_release_hash_doubleopen(self):
        """Blocks the event and releases it when hashed, double mixed open."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[self.tf], 1)
        self.assertNotIn(self.tf, self.nanny._hashing)

        self.eq.push("FS_FILE_CLOSE_WRITE", path=self.tf)

        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_WRITE", self.tf)]
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._opened)
        self.assertIn(self.tf, self.nanny._hashing)

        self.eq.push("FS_FILE_OPEN", path=self.tf)

        self.assertEqual(self.listener.events(), [("FS_FILE_OPEN", self.tf)])
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[self.tf], 1)
        self.assertIn(self.tf, self.nanny._hashing)
        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=self.tf)

        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_NOWRITE", self.tf)]
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._opened)
        self.assertIn(self.tf, self.nanny._hashing)

        self.eq.push(
            "HQ_HASH_NEW",
            path=self.tf,
            hash="hash",
            crc32="crc",
            size="size",
            stat="stt",
        )
        self.assertEqual(
            self.listener.events(),
            [
                ("HQ_HASH_NEW", self.tf, "crc", "hash", "size", "stt"),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._opened)
        self.assertNotIn(self.tf, self.nanny._hashing)

    def test_blocks_release_close_doubleopen(self):
        """Blocks the event and releases it when close, double open."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )
        self.eq.push("FS_FILE_OPEN", path=self.tf)

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
                ("FS_FILE_OPEN", self.tf),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[self.tf], 2)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=self.tf)

        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_NOWRITE", self.tf)]
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[self.tf], 1)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=self.tf)
        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_CLOSE_NOWRITE", self.tf),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._opened)

    def test_blocks_release_close_differentfiles(self):
        """Blocks the event and releases it when close, several files."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path="other")
        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_NOWRITE", "other")]
        )
        self.assertIn(self.tf, self.nanny._blocked)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=self.tf)
        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_CLOSE_NOWRITE", self.tf),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)

    @defer.inlineCallbacks
    def test_blocks_release_hashdone(self):
        """Blocks the event and releases it when the hash is done."""

        yield self.insert_in_hq(self.tf, "nodeid")
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash")],
        )
        self.assertIn(self.tf, self.nanny._blocked)

        yield self.release_hq()
        self.eq.push(
            "HQ_HASH_NEW",
            path=self.tf,
            hash="hash",
            crc32="crc",
            size="siz",
            stat="stt",
        )
        self.assertEqual(
            self.listener.events(),
            [
                ("HQ_HASH_NEW", self.tf, "crc", "hash", "siz", "stt"),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)

    @defer.inlineCallbacks
    def test_blocks_closewrite_hashdone(self):
        """Knows that is hashing also because of CLOSE_WRITE."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._hashing)

        yield self.insert_in_hq(self.tf, "nodeid")
        self.eq.push("FS_FILE_CLOSE_WRITE", path=self.tf)

        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_WRITE", self.tf)]
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertIn(self.tf, self.nanny._hashing)

        yield self.release_hq()
        self.eq.push(
            "HQ_HASH_NEW",
            path=self.tf,
            hash="hash",
            crc32="crc",
            size="siz",
            stat="stt",
        )
        self.assertEqual(
            self.listener.events(),
            [
                ("HQ_HASH_NEW", self.tf, "crc", "hash", "siz", "stt"),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._hashing)

    def test_create_discards(self):
        """The block and open count is discarded when file created."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[self.tf], 1)

        self.eq.push("FS_FILE_CREATE", path=self.tf)
        self.assertEqual(self.listener.events(), [("FS_FILE_CREATE", self.tf)])
        self.assertNotIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._opened)

    def test_create_noblocked(self):
        """Create is received, nothing was blocked."""
        self.eq.push("FS_FILE_CREATE", path=self.tf)
        self.assertEqual(self.listener.events(), [("FS_FILE_CREATE", self.tf)])

    def test_delete_discards(self):
        """The block and open count is discarded when file deleted."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[self.tf], 1)

        self.eq.push("FS_FILE_DELETE", path=self.tf)
        self.assertEqual(self.listener.events(), [("FS_FILE_DELETE", self.tf)])
        self.assertNotIn(self.tf, self.nanny._blocked)
        self.assertNotIn(self.tf, self.nanny._opened)

    def test_delete_noblocked(self):
        """Delete is received, nothing was blocked."""
        self.eq.push("FS_FILE_DELETE", path=self.tf)
        self.assertEqual(self.listener.events(), [("FS_FILE_DELETE", self.tf)])

    def test_file_move_changeblock(self):
        """Move event affects the blocked stuff."""
        # prepare the second file
        tf2 = self.tf + "2"
        self.fsm.create(tf2, "")
        self.fsm.set_node_id(tf2, "nodeid2")

        # initial events
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)

        self.eq.push("FS_FILE_MOVE", path_from=self.tf, path_to=tf2)

        self.assertEqual(
            self.listener.events(), [("FS_FILE_MOVE", self.tf, tf2)]
        )
        self.assertNotIn(self.tf, self.nanny._blocked)
        self.assertIn(tf2, self.nanny._blocked)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=tf2)
        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_CLOSE_NOWRITE", tf2),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(tf2, self.nanny._blocked)

    @skip_if_win32_missing_fs_event
    def test_dir_move_changeblock(self):
        """Move event affects the blocked stuff."""
        # create several files with tricky names
        tf1 = os.path.join(self.usrdir, "fo123", "tfile")
        tf2 = os.path.join(self.usrdir, "fo12", "tfile")
        tf3 = os.path.join(self.usrdir, "fo1", "tfile")
        tf4 = os.path.join(self.usrdir, "fo")
        tf5 = os.path.join(self.usrdir, "fo1234")

        dir_from = os.path.join(self.usrdir, "fo12")
        dir_to = os.path.join(self.usrdir, "zar")
        newtf2 = os.path.join(self.usrdir, "zar", "tfile")

        # create them and generate the initial events for all of them
        for i, tf in enumerate((tf1, tf2, tf3, tf4, tf5)):
            self.fsm.create(tf, "")
            self.fsm.set_node_id(tf, "nodeid" + str(i + 1))
            self.eq.push("FS_FILE_OPEN", path=tf)
            self.eq.push(
                "AQ_DOWNLOAD_COMMIT",
                share_id="",
                node_id="nodeid" + str(i + 1),
                server_hash="s_hash",
            )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", tf1),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid1", "s_hash"),
                ("FS_FILE_OPEN", tf2),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid2", "s_hash"),
                ("FS_FILE_OPEN", tf3),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid3", "s_hash"),
                ("FS_FILE_OPEN", tf4),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid4", "s_hash"),
                ("FS_FILE_OPEN", tf5),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid5", "s_hash"),
            ],
        )
        self.assertIn(tf1, self.nanny._blocked)
        self.assertIn(tf2, self.nanny._blocked)
        self.assertIn(tf3, self.nanny._blocked)
        self.assertIn(tf4, self.nanny._blocked)
        self.assertIn(tf5, self.nanny._blocked)

        self.eq.push("FS_DIR_MOVE", path_from=dir_from, path_to=dir_to)
        self.assertEqual(
            self.listener.events(), [("FS_DIR_MOVE", dir_from, dir_to)]
        )
        self.assertIn(tf1, self.nanny._blocked)
        self.assertNotIn(tf2, self.nanny._blocked)
        self.assertIn(newtf2, self.nanny._blocked)
        self.assertIn(tf3, self.nanny._blocked)
        self.assertIn(tf4, self.nanny._blocked)
        self.assertIn(tf5, self.nanny._blocked)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=newtf2)
        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_CLOSE_NOWRITE", newtf2),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid2", "s_hash"),
            ],
        )
        self.assertIn(tf1, self.nanny._blocked)
        self.assertNotIn(tf2, self.nanny._blocked)
        self.assertNotIn(newtf2, self.nanny._blocked)
        self.assertIn(tf3, self.nanny._blocked)
        self.assertIn(tf4, self.nanny._blocked)
        self.assertIn(tf5, self.nanny._blocked)

    @skip_if_win32_missing_fs_event
    def test_complex(self):
        """Open, Open, Close, MoveFile, Open, MoveDir, Close, Close... test!"""
        # create a file inside a directory
        dir_from = os.path.join(self.usrdir, "foo")
        tf1 = os.path.join(self.usrdir, "foo", "tfile1")
        tf2 = os.path.join(self.usrdir, "foo", "tfile2")
        dir_to = os.path.join(self.usrdir, "zar")
        newtf2 = os.path.join(self.usrdir, "zar", "tfile2")

        # create the file and generate the initial events
        self.fsm.create(tf1, "")
        self.fsm.set_node_id(tf1, "nodeid")

        self.eq.push("FS_FILE_OPEN", path=tf1)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )
        self.eq.push("FS_FILE_OPEN", path=tf1)

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", tf1),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
                ("FS_FILE_OPEN", tf1),
            ],
        )
        self.assertIn(tf1, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[tf1], 2)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=tf1)

        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_NOWRITE", tf1)]
        )
        self.assertIn(tf1, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[tf1], 1)

        self.eq.push("FS_FILE_MOVE", path_from=tf1, path_to=tf2)

        self.assertEqual(self.listener.events(), [("FS_FILE_MOVE", tf1, tf2)])
        self.assertNotIn(tf1, self.nanny._blocked)
        self.assertIn(tf2, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[tf2], 1)

        self.eq.push("FS_FILE_OPEN", path=tf2)
        self.eq.push("FS_DIR_MOVE", path_from=dir_from, path_to=dir_to)

        self.assertEqual(
            self.listener.events(),
            [("FS_FILE_OPEN", tf2), ("FS_DIR_MOVE", dir_from, dir_to)],
        )
        self.assertNotIn(tf2, self.nanny._blocked)
        self.assertIn(newtf2, self.nanny._blocked)
        self.assertEqual(self.nanny._opened[newtf2], 2)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=newtf2)
        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=newtf2)

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_CLOSE_NOWRITE", newtf2),
                ("FS_FILE_CLOSE_NOWRITE", newtf2),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(newtf2, self.nanny._blocked)
        self.assertNotIn(newtf2, self.nanny._opened)

    @defer.inlineCallbacks
    def test_mixed_hash_close(self):
        """It's ready to release according to hashing, but it's opened."""
        yield self.insert_in_hq(self.tf, "nodeid")
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash")],
        )
        self.assertIn(self.tf, self.nanny._blocked)

        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.assertEqual(self.listener.events(), [("FS_FILE_OPEN", self.tf)])
        self.assertIn(self.tf, self.nanny._blocked)

        yield self.release_hq()
        self.eq.push(
            "HQ_HASH_NEW",
            path=self.tf,
            hash="hash",
            crc32="crc",
            size="siz",
            stat="stt",
        )
        self.assertEqual(
            self.listener.events(),
            [("HQ_HASH_NEW", self.tf, "crc", "hash", "siz", "stt")],
        )
        self.assertIn(self.tf, self.nanny._blocked)

        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=self.tf)
        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_CLOSE_NOWRITE", self.tf),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)

    @defer.inlineCallbacks
    def test_mixed_close_hash(self):
        """It's ready to release according to open/close, but it's hashing."""
        self.eq.push("FS_FILE_OPEN", path=self.tf)
        self.eq.push(
            "AQ_DOWNLOAD_COMMIT",
            share_id="",
            node_id="nodeid",
            server_hash="s_hash",
        )

        self.assertEqual(
            self.listener.events(),
            [
                ("FS_FILE_OPEN", self.tf),
                ("AQ_DOWNLOAD_COMMIT", "", "nodeid", "s_hash"),
            ],
        )
        self.assertIn(self.tf, self.nanny._blocked)

        yield self.insert_in_hq(self.tf, "nodeid")
        self.eq.push("FS_FILE_CLOSE_NOWRITE", path=self.tf)
        self.assertEqual(
            self.listener.events(), [("FS_FILE_CLOSE_NOWRITE", self.tf)]
        )
        self.assertIn(self.tf, self.nanny._blocked)

        yield self.release_hq()
        self.eq.push(
            "HQ_HASH_NEW",
            path=self.tf,
            hash="hash",
            crc32="crc",
            size="siz",
            stat="stt",
        )
        self.assertEqual(
            self.listener.events(),
            [
                ("HQ_HASH_NEW", self.tf, "crc", "hash", "siz", "stt"),
                ("AQ_DOWNLOAD_FINISHED", "", "nodeid", "s_hash"),
            ],
        )
        self.assertNotIn(self.tf, self.nanny._blocked)


class EventListenersTests(unittest.TestCase):
    """Check the event listener API."""

    def test_event_listener(self):
        """All event listeners should define methods with correct signature."""
        cls = events_nanny.DownloadFinishedNanny
        for evtname, evtargs in event_queue.EVENTS.items():
            meth = getattr(cls, 'handle_' + evtname, None)
            if meth is not None:
                defined_args = inspect.getargspec(meth)[0]
                self.assertEqual(defined_args[0], 'self')
                self.assertEqual(set(defined_args[1:]), set(evtargs))
