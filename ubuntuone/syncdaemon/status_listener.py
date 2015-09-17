# ubuntuone.syncdaemon.status_listener
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
"""Listener for event queue that updates the UI to show syncdaemon status."""

from ubuntuone.status.aggregator import StatusFrontend
from ubuntuone.syncdaemon import (
    action_queue,
    config,
    RECENT_TRANSFERS,
    UPLOADING,
    DOWNLOADING
)
from ubuntuone.syncdaemon.interaction_interfaces import (
    get_share_dict, get_udf_dict)
from ubuntuone.syncdaemon.volume_manager import UDF, Root


def should_start_listener():
    """Check if the status listener should be started."""
    # TODO: look this up in some configuration object
    return True


def get_listener(fsm, vm, syncdaemon_service=None):
    """Return an instance of the status listener, or None if turned off."""
    if should_start_listener():
        status_frontend = StatusFrontend(service=syncdaemon_service)
        return StatusListener(fsm, vm, status_frontend)
    else:
        return None


#TODO: hookup the shutdown of the listener to the cleanup in the aggregator
class StatusListener(object):
    """SD listener for EQ events that turns them into status updates."""

    _show_all_notifications = True

    def __init__(self, fsm, vm, status_frontend):
        """Initialize this instance with the FSM and VM."""
        self.fsm = fsm
        self.vm = vm
        self.status_frontend = status_frontend
        user_conf = config.get_user_config()
        self.show_all_notifications = user_conf.get_show_all_notifications()

    def menu_data(self):
        """Return the info necessary to construct the sync menu."""
        uploading = self.status_frontend.files_uploading()
        downloading = self.status_frontend.files_downloading()
        transfers = self.status_frontend.recent_transfers()
        data = {RECENT_TRANSFERS: transfers,
                UPLOADING: uploading,
                DOWNLOADING: downloading}
        return data

    def get_show_all_notifications(self):
        """Get the value of show_all_notifications."""
        return self._show_all_notifications

    def set_show_all_notifications(self, value):
        """Set the value of show_all_notifications."""
        self._show_all_notifications = value
        self.status_frontend.set_show_all_notifications(value)

    show_all_notifications = property(get_show_all_notifications,
                                      set_show_all_notifications)

    # pylint: disable=W0613
    def handle_AQ_CHANGE_PUBLIC_ACCESS_OK(self, share_id, node_id, is_public,
                                          public_url):
        """The status of a published resource changed."""
        if is_public:
            self.status_frontend.file_published(public_url)
        else:
            self.status_frontend.file_unpublished(public_url)

    def handle_AQ_UPLOAD_FILE_PROGRESS(self, share_id, node_id,
                                       n_bytes_written, deflated_size):
        """Progress has been made on an upload."""
        self.status_frontend.progress_made(
            share_id, node_id, n_bytes_written, deflated_size)

    def handle_AQ_DOWNLOAD_FILE_PROGRESS(self, share_id, node_id,
                                         n_bytes_read, deflated_size):
        """Progress has been made on an upload."""
        self.status_frontend.progress_made(
            share_id, node_id, n_bytes_read, deflated_size)
    # pylint: enable=W0613

    def handle_SYS_QUEUE_ADDED(self, command):
        """A command has been added to the queue."""
        if isinstance(command, action_queue.Download):
            self.status_frontend.download_started(command)
        elif isinstance(command, action_queue.Upload):
            self.status_frontend.upload_started(command)

    def handle_SYS_QUEUE_REMOVED(self, command):
        """A command has been removed from the queue."""
        if isinstance(command, action_queue.Download):
            self.status_frontend.download_finished(command)
        elif isinstance(command, action_queue.Upload):
            self.status_frontend.upload_finished(command)

    def handle_SYS_QUEUE_DONE(self):
        """The queue has finished processing everything."""
        self.status_frontend.queue_done()

    def handle_VM_SHARE_CREATED(self, share_id):
        """A new share is available for subscription."""
        share = self.vm.get_volume(share_id)
        self.status_frontend.new_share_available(share)

    def handle_VM_UDF_CREATED(self, udf):
        """A new udf is available for subscription."""
        self.status_frontend.new_udf_available(udf)

    def handle_SYS_CONNECTION_LOST(self):
        """The client lost the connection to the server."""
        self.status_frontend.server_connection_lost()

    def handle_SYS_CONNECTION_MADE(self):
        """The client connected to the server."""
        self.status_frontend.server_connection_made()

    def handle_SYS_QUOTA_EXCEEDED(self, volume_id, free_bytes):
        """Handle the SYS_QUOTA_EXCEEDED event."""
        volume = self.vm.get_volume(str(volume_id))
        volume_dict = {}
        if isinstance(volume, UDF):
            volume_dict = get_udf_dict(volume)
            to_call = self.status_frontend.udf_quota_exceeded
        elif isinstance(volume, Root):
            volume_dict = get_share_dict(volume)
            to_call = self.status_frontend.root_quota_exceeded
        else:
            volume_dict = get_share_dict(volume)
            to_call = self.status_frontend.share_quota_exceeded
        volume_dict['free_bytes'] = str(free_bytes)
        to_call(volume_dict)
