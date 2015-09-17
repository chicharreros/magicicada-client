# tests.syncdaemon.test_status_listener
#
# Author: Alejandro J. Cura <alecu@canonical.com>
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
"""Test the syncdaemon status listener."""

import os

from twisted.internet import defer

from contrib.testing.testcase import FakeMainTestCase, BaseTwistedTestCase
from ubuntuone.syncdaemon import config, status_listener
from ubuntuone.syncdaemon.volume_manager import Share, UDF, get_udf_path


class GetListenerTestCase(BaseTwistedTestCase):
    """The status listener is created."""

    def test_returns_listener(self):
        """get_listener returns a listener if status reporting is enabled."""
        self.patch(status_listener, "should_start_listener", lambda: True)
        self.patch(status_listener, "StatusFrontend", FakeStatusFrontend)
        fsm = object()
        vm = object()
        listener = status_listener.get_listener(fsm, vm)
        self.assertIsInstance(listener, status_listener.StatusListener)
        self.assertEqual(listener.fsm, fsm)
        self.assertEqual(listener.vm, vm)
        self.assertNotEqual(listener.status_frontend, None)


def listen_for(event_q, event, callback, count=1, collect=False):
    """Setup a EQ listener for the specified event."""
    class Listener(object):
        """A basic listener to handle the pushed event."""

        def __init__(self):
            self.hits = 0
            self.events = []

        def _handle_event(self, *args, **kwargs):
            self.hits += 1
            if collect:
                self.events.append((args, kwargs))
            if self.hits == count:
                event_q.unsubscribe(self)
                if collect:
                    callback(self.events)
                elif kwargs:
                    callback((args, kwargs))
                else:
                    callback(args)

    listener = Listener()
    setattr(listener, 'handle_' + event, listener._handle_event)
    event_q.subscribe(listener)
    return listener


class FakeStatusFrontend(object):
    """A fake status frontend."""

    def __init__(self, *args, **kwargs):
        """Initialize this instance."""
        self.call_log = []

    def __getattr__(self, f_name):
        """Return a method that will log it's args when called."""

        def f(*args, **kwargs):
            """Log the args I'm passed."""
            self.call_log.append((f_name, args, kwargs))

        return f


class StatusListenerTestCase(FakeMainTestCase):
    """Tests for StatusListener."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this instance."""
        yield super(StatusListenerTestCase, self).setUp()
        self.status_frontend = FakeStatusFrontend()
        self.listener = status_listener.StatusListener(self.fs, self.vm,
                                                       self.status_frontend)
        self.event_q.subscribe(self.listener)

    def _listen_for(self, *args, **kwargs):
        return listen_for(self.main.event_q, *args, **kwargs)


class StatusListenerConfigTestCase(StatusListenerTestCase):
    """Test the config of the status listener."""

    def test_show_all_notifications_calls_frontend(self):
        """Changes in the value of notifications are sent to the frontend."""
        self.listener.show_all_notifications = True
        call = ("set_show_all_notifications", (True,), {})
        self.assertIn(call, self.status_frontend.call_log)

    def test_show_all_notifications_true(self):
        """The value of show_all_notifications is set to True."""
        user_conf = config.get_user_config()
        user_conf.set_show_all_notifications(True)
        listener = status_listener.StatusListener(None, None,
                                                  self.status_frontend)
        self.assertTrue(listener.show_all_notifications)

    def test_show_all_notifications_false(self):
        """The value of show_all_notifications is set to False."""
        user_conf = config.get_user_config()
        user_conf.set_show_all_notifications(False)
        listener = status_listener.StatusListener(None, None,
                                                  self.status_frontend)
        self.assertFalse(listener.show_all_notifications)


class PublicFilesStatusTestCase(StatusListenerTestCase):
    """Public files events are passed to the status object."""

    @defer.inlineCallbacks
    def test_publish_url_is_forwarded(self):
        """Publishing a file with a url is forwarded."""
        share_id = "share"
        node_id = "node_id"
        is_public = True
        public_url = 'http://example.com/foo.mp3'

        share_path = os.path.join(self.shares_dir, 'share')
        yield self.main.vm.add_share(Share(path=share_path, volume_id='share',
                                           other_username='other username'))
        path = os.path.join(share_path, "foo.mp3")
        self.main.fs.create(path, str(share_id))
        self.main.fs.set_node_id(path, str(node_id))

        d = defer.Deferred()
        self._listen_for('AQ_CHANGE_PUBLIC_ACCESS_OK', d.callback)
        self.main.event_q.push('AQ_CHANGE_PUBLIC_ACCESS_OK',
                               share_id=share_id, node_id=node_id,
                               is_public=is_public, public_url=public_url)
        yield d
        call = ("file_published", (public_url,), {})
        self.assertIn(call, self.status_frontend.call_log)

    @defer.inlineCallbacks
    def test_unpublish_url_is_forwarded(self):
        """Unpublishing a file with a url is forwarded."""
        share_id = "share"
        node_id = "node_id"
        is_public = False
        public_url = 'http://example.com/foo.mp3'

        share_path = os.path.join(self.shares_dir, 'share')
        yield self.main.vm.add_share(Share(path=share_path, volume_id='share',
                                           other_username='other username'))
        path = os.path.join(share_path, "foo.mp3")
        self.main.fs.create(path, str(share_id))
        self.main.fs.set_node_id(path, str(node_id))

        d = defer.Deferred()
        self._listen_for('AQ_CHANGE_PUBLIC_ACCESS_OK', d.callback)
        self.main.event_q.push('AQ_CHANGE_PUBLIC_ACCESS_OK',
                               share_id=share_id, node_id=node_id,
                               is_public=is_public, public_url=public_url)
        yield d
        call = ("file_unpublished", (public_url,), {})
        self.assertIn(call, self.status_frontend.call_log)


class FakeTransfer(object):
    """A fake action queue command."""


class ProgressStatusTestCase(StatusListenerTestCase):
    """Upload/Download Progress events are passed to the status object."""

    @defer.inlineCallbacks
    def test_upload_progress_is_forwarded(self):
        """An upload progress event is forwarded."""
        share_id = "share"
        node_id = "node_id"
        n_bytes_written = 100
        deflated_size = 1000
        d = defer.Deferred()
        self._listen_for('AQ_UPLOAD_FILE_PROGRESS', d.callback)
        self.main.event_q.push(
            'AQ_UPLOAD_FILE_PROGRESS', share_id=share_id, node_id=node_id,
            n_bytes_written=n_bytes_written, deflated_size=deflated_size)
        yield d
        call = (
            "progress_made",
            (share_id, node_id, n_bytes_written, deflated_size), {})
        self.assertIn(call, self.status_frontend.call_log)

    @defer.inlineCallbacks
    def test_download_progress_is_forwarded(self):
        """A download progress event is forwarded."""
        share_id = "share"
        node_id = "node_id"
        n_bytes_read = 100
        deflated_size = 1000
        d = defer.Deferred()
        self._listen_for('AQ_DOWNLOAD_FILE_PROGRESS', d.callback)
        self.main.event_q.push(
            'AQ_DOWNLOAD_FILE_PROGRESS', share_id=share_id, node_id=node_id,
            n_bytes_read=n_bytes_read, deflated_size=deflated_size)
        yield d
        call = (
            "progress_made",
            (share_id, node_id, n_bytes_read, deflated_size), {})
        self.assertIn(call, self.status_frontend.call_log)


class QueueChangedStatusTestCase(StatusListenerTestCase):
    """Queue changed events are passed to the status object."""

    @defer.inlineCallbacks
    def test_download_added_is_forwarded(self):
        """A Download added event is forwarded."""
        self.patch(status_listener.action_queue, "Download", FakeTransfer)
        fake_command = FakeTransfer()

        d = defer.Deferred()
        self._listen_for('SYS_QUEUE_ADDED', d.callback)
        self.main.event_q.push('SYS_QUEUE_ADDED', command=fake_command)
        yield d

        call = ("download_started", (fake_command,), {})
        self.assertIn(call, self.status_frontend.call_log)

    @defer.inlineCallbacks
    def test_download_removed_is_forwarded(self):
        """A Download removed event is forwarded."""
        self.patch(status_listener.action_queue, "Download", FakeTransfer)
        fake_command = FakeTransfer()

        d = defer.Deferred()
        self._listen_for('SYS_QUEUE_REMOVED', d.callback)
        self.main.event_q.push('SYS_QUEUE_REMOVED', command=fake_command)
        yield d

        call = ("download_finished", (fake_command,), {})
        self.assertIn(call, self.status_frontend.call_log)

    @defer.inlineCallbacks
    def test_upload_added_is_forwarded(self):
        """A Upload added event is forwarded."""
        self.patch(status_listener.action_queue, "Upload", FakeTransfer)
        fake_command = FakeTransfer()

        d = defer.Deferred()
        self._listen_for('SYS_QUEUE_ADDED', d.callback)
        self.main.event_q.push('SYS_QUEUE_ADDED', command=fake_command)
        yield d

        call = ("upload_started", (fake_command,), {})
        self.assertIn(call, self.status_frontend.call_log)

    @defer.inlineCallbacks
    def test_upload_removed_is_forwarded(self):
        """A Upload removed event is forwarded."""
        self.patch(status_listener.action_queue, "Upload", FakeTransfer)
        fake_command = FakeTransfer()

        d = defer.Deferred()
        self._listen_for('SYS_QUEUE_REMOVED', d.callback)
        self.main.event_q.push('SYS_QUEUE_REMOVED', command=fake_command)
        yield d

        call = ("upload_finished", (fake_command,), {})
        self.assertIn(call, self.status_frontend.call_log)

    @defer.inlineCallbacks
    def test_queue_done_is_forwarded(self):
        """A queue done event is forwarded."""
        d = defer.Deferred()
        self._listen_for('SYS_QUEUE_DONE', d.callback)
        self.main.event_q.push('SYS_QUEUE_DONE')
        yield d

        call = ("queue_done", (), {})
        self.assertIn(call, self.status_frontend.call_log)


class NewVolumesStatusTestCase(StatusListenerTestCase):
    """New volumes events are passed to the status object."""

    @defer.inlineCallbacks
    def test_new_unsubscribed_share_is_forwarded(self):
        """A new unsubscribed share event is forwarded."""
        SHARE_ID = "fake share id"
        d = defer.Deferred()
        share = Share(volume_id=SHARE_ID)
        yield self.main.vm.add_share(share)
        self._listen_for('VM_SHARE_CREATED', d.callback)
        self.main.event_q.push('VM_SHARE_CREATED', share_id=share)
        yield d
        call = ("new_share_available", (share,), {})
        self.assertIn(call, self.status_frontend.call_log)

    @defer.inlineCallbacks
    def test_new_unsubscribed_udf_is_forwarded(self):
        """A new unsubscribed udf event is forwarded."""
        d = defer.Deferred()
        udf = UDF()
        self._listen_for('VM_UDF_CREATED', d.callback)
        self.main.event_q.push('VM_UDF_CREATED', udf=udf)
        yield d
        call = ("new_udf_available", (udf,), {})
        self.assertIn(call, self.status_frontend.call_log)


class NetworkEventStatusTestCase(StatusListenerTestCase):
    """The connection to the server is lost and restored."""

    @defer.inlineCallbacks
    def test_connection_lost(self):
        """The connection to the server is lost."""
        d = defer.Deferred()
        self._listen_for('SYS_CONNECTION_LOST', d.callback)
        self.main.event_q.push('SYS_CONNECTION_LOST')
        yield d
        call = ("server_connection_lost", (), {})
        self.assertIn(call, self.status_frontend.call_log)

    @defer.inlineCallbacks
    def test_connection_made_is_forwarded(self):
        """The connection to the server is made."""
        d = defer.Deferred()
        self._listen_for('SYS_CONNECTION_MADE', d.callback)
        self.main.event_q.push('SYS_CONNECTION_MADE')
        yield d
        call = ("server_connection_made", (), {})
        self.assertIn(call, self.status_frontend.call_log)


class QuotaExceededStatusTestCase(StatusListenerTestCase):
    """Quota for UDFs/Shares/Root exceeded."""

    @defer.inlineCallbacks
    def test_root_quota_exceeded(self):
        """Quota for root exceeded."""
        d = defer.Deferred()
        root = self.main.vm.root
        BYTES = 0
        self._listen_for('SYS_QUOTA_EXCEEDED', d.callback)
        self.main.event_q.push(
            'SYS_QUOTA_EXCEEDED', volume_id=root.volume_id, free_bytes=BYTES)
        yield d
        self.assertIn("root_quota_exceeded", (
            call[0] for call in self.status_frontend.call_log))

    @defer.inlineCallbacks
    def test_share_quota_exceeded(self):
        """Quota for a share exceeded."""
        SHARE_ID = 'fake share id'
        BYTES = 0
        d = defer.Deferred()
        share = Share(volume_id=SHARE_ID)
        yield self.main.vm.add_share(share)
        self._listen_for('SYS_QUOTA_EXCEEDED', d.callback)
        self.main.event_q.push(
            'SYS_QUOTA_EXCEEDED', volume_id=SHARE_ID, free_bytes=BYTES)
        yield d
        self.assertIn("share_quota_exceeded", (
            call[0] for call in self.status_frontend.call_log))

    @defer.inlineCallbacks
    def test_udf_quota_exceeded(self):
        """Quota for a UDF exceeded."""
        UDF_ID = 'fake udf id'
        suggested_path = u'~/test_udf_quota_exceeded/bar/baz'
        PATH = get_udf_path(suggested_path)
        BYTES = 0
        d = defer.Deferred()
        udf = UDF(volume_id=UDF_ID, node_id='test',
                  suggested_path=suggested_path, path=PATH, subscribed=True)
        yield self.main.vm.add_udf(udf)
        self._listen_for('SYS_QUOTA_EXCEEDED', d.callback)
        self.main.event_q.push(
            'SYS_QUOTA_EXCEEDED', volume_id=UDF_ID, free_bytes=BYTES)
        yield d
        self.assertIn(
            "udf_quota_exceeded",
            [call[0] for call in self.status_frontend.call_log])
