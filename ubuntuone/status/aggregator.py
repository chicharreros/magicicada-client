# ubuntuone.status.aggregator
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
"""Aggregate status events."""

import itertools
import operator
import os
from collections import deque, Callable

import gettext

from twisted.internet import reactor, defer

from ubuntuone.clientdefs import GETTEXT_PACKAGE
from ubuntuone.status.logger import logger
from ubuntuone.platform import (
    notification,
    sync_menu
)
from ubuntuone.platform.launcher import UbuntuOneLauncher, DummyLauncher

ONE_DAY = 24 * 60 * 60
Q_ = lambda string: gettext.dgettext(GETTEXT_PACKAGE, string)

UBUNTUONE_TITLE = Q_("Magicicada")
UBUNTUONE_END = Q_(
    "Magicicada file services will be shutting down on June 1st, 2014.\n"
    "Thanks for your support.")
NEW_UDFS_SENDER = Q_("New cloud folder(s) available")
FINAL_COMPLETED = Q_("File synchronization completed.")

PROGRESS_COMPLETED = Q_("%(percentage_completed)d%% completed.")
FILE_SYNC_IN_PROGRESS = Q_("File synchronization in progress")

SHARE_QUOTA_EXCEEDED = Q_(
    'There is no available space on the folder:\n"%s" shared by %s')


def alert_user():
    """Set the launcher to urgent to alert the user."""
    launcher = UbuntuOneLauncher()
    launcher.set_urgent()


def files_being_uploaded(filename, files_uploading):
    """Get the i18n string for files being uploaded."""
    other_files = files_uploading - 1
    if other_files < 1:
        return Q_(
            "'%(filename)s' is being uploaded to your personal cloud.") % {
            'filename': filename}
    format_args = {
        "filename": filename, "other_files": other_files}
    return gettext.dngettext(
        GETTEXT_PACKAGE,
        "'%(filename)s' and %(other_files)d other file are being "
        "uploaded to your personal cloud.",
        "'%(filename)s' and %(other_files)d other files are being "
        "uploaded to your personal cloud.", other_files) % format_args


def files_being_downloaded(filename, files_downloading):
    """Get the i18n string for files being downloaded."""
    other_files = files_downloading - 1
    if other_files < 1:
        return Q_(
            "'%(filename)s' is being downloaded to your computer.") % {
            'filename': filename}
    format_args = {
        "filename": filename, "other_files": other_files}
    return gettext.dngettext(
        GETTEXT_PACKAGE,
        "'%(filename)s' and %(other_files)d other file are being "
        "downloaded to your computer.",
        "'%(filename)s' and %(other_files)d other files are being "
        "downloaded to your computer.", other_files) % format_args


def files_were_uploaded(filename, upload_done):
    """Get the i18n string for files that were uploaded."""
    other_files = upload_done - 1
    if other_files < 1:
        return Q_(
            "'%(filename)s' was uploaded to your personal cloud.") % {
            'filename': filename}
    format_args = {
        'filename': filename, 'other_files': other_files}
    return gettext.dngettext(
        GETTEXT_PACKAGE,
        "'%(filename)s' and %(other_files)d other file were uploaded to "
        "your personal cloud.",
        "'%(filename)s' and %(other_files)d other files were uploaded "
        "to your personal cloud.", other_files) % format_args


def files_were_downloaded(filename, download_done):
    """Get the i18n string for files that were downloaded."""
    other_files = download_done - 1
    if other_files < 1:
        return Q_(
            "'%(filename)s' was downloaded to your computer.") % {
            'filename': filename}
    format_args = {
        'filename': filename, 'other_files': other_files}
    return gettext.dngettext(
        GETTEXT_PACKAGE,
        "'%(filename)s' and %(other_files)d other file were "
        "downloaded to your computer.",
        "'%(filename)s' and %(other_files)d other files were "
        "downloaded to your computer.", other_files) % format_args


class ToggleableNotification(object):
    """A controller for notifications that can be turned off."""

    def __init__(self, notification_switch):
        """Initialize this instance."""
        self.notification_switch = notification_switch
        self.notification = notification.Notification()

    def send_notification(self, *args):
        """Passthru the notification."""
        if self.notification_switch.enabled:
            return self.notification.send_notification(*args)


class NotificationSwitch(object):
    """A switch that turns notifications on and off."""

    enabled = True

    def __init__(self):
        self.toggleable_notification = ToggleableNotification(self)

    def get_notification(self):
        """Return a new notification instance."""
        return self.toggleable_notification

    def enable_notifications(self):
        """Turn the switch on."""
        self.enabled = True

    def disable_notifications(self):
        """Turn the switch off."""
        self.enabled = False


class StatusEvent(object):
    """An event representing a status change."""

    MESSAGE_ONE = None  # to be defined in child classes
    WEIGHT = 99
    DO_NOT_INSTANCE = "Do not instance this class, only children."

    def __init__(self, **kwargs):
        """Initialize this instance."""
        assert type(self) != StatusEvent, self.DO_NOT_INSTANCE
        self.kwargs = kwargs

    def one(self):
        """A message if this is the only event of this type."""
        return self.MESSAGE_ONE


class FilePublishingStatus(StatusEvent):
    """Files that are made public with a url."""

    MESSAGE_ONE = Q_("A share link was just created at %(new_public_url)s")

    WEIGHT = 50

    def one(self):
        """Show the url if only one event of this type."""
        return self.MESSAGE_ONE % self.kwargs

    def many(self, events):
        """Show the number of files if many event of this type."""
        no_of_files = len(events)
        gettext.dngettext(
            GETTEXT_PACKAGE,
            "%(event_count)d file was just shared.",
            "%(event_count)d files were just shared.",
            no_of_files) % {'event_count': no_of_files}


class FileUnpublishingStatus(StatusEvent):
    """Files that have stopped being published."""

    MESSAGE_ONE = Q_("A share link is no longer available")
    WEIGHT = 51

    def many(self, events):
        """Show the number of files if many event of this type."""
        no_of_files = len(events)
        gettext.dngettext(
            GETTEXT_PACKAGE,
            "%(event_count)d file is no longer shared.",
            "%(event_count)d files are no longer shared.",
            no_of_files) % {'event_count': no_of_files}


class FolderAvailableStatus(StatusEvent):
    """Folders available for subscription."""

    WEIGHT = 60

    def many(self, events):
        """Show the number of files if many event of this type."""
        no_of_files = len(events)
        gettext.dngettext(
            GETTEXT_PACKAGE,
            "Found %(event_count)d new cloud folder.",
            "Found %(event_count)d new cloud folders.",
            no_of_files) % {'event_count': no_of_files}


class ShareAvailableStatus(FolderAvailableStatus):
    """A Share is available for subscription."""

    MESSAGE_ONE = Q_("New cloud folder available: '%(folder_name)s' "
                     "shared by %(other_user_name)s")

    def one(self):
        """Show the folder information."""
        volume = self.kwargs["share"]
        format_args = {
            "folder_name": volume.name,
            "other_user_name": volume.other_visible_name,
        }
        return self.MESSAGE_ONE % format_args


class UDFAvailableStatus(FolderAvailableStatus):
    """An UDF is available for subscription."""

    MESSAGE_ONE = Q_("New cloud folder available: '%(folder_name)s'")

    def one(self):
        """Show the folder information."""
        volume = self.kwargs["udf"]
        format_args = {"folder_name": volume.suggested_path}
        return self.MESSAGE_ONE % format_args


class ConnectionStatusEvent(StatusEvent):
    """The connection to the server changed status."""

    WEIGHT = 30

    def many(self, events):
        """Only the last message if there are many events of this type."""
        return events[-1].one()


class ConnectionLostStatus(ConnectionStatusEvent):
    """The connection to the server was lost."""

    MESSAGE_ONE = Q_("The connection to the server was lost.")


class ConnectionMadeStatus(ConnectionStatusEvent):
    """The connection to the server was made."""

    MESSAGE_ONE = Q_("The connection to the server was restored.")


class Timer(defer.Deferred):
    """A deferred that fires past a given delay."""

    def __init__(self, delay, clock=reactor):
        """Initialize this instance."""
        defer.Deferred.__init__(self)
        self.clock = clock
        self.delay = delay
        self.delay_call = self.clock.callLater(delay, self.callback)

    def cancel_if_active(self, call):
        """Cancel a call if it is active."""
        if call.active():
            call.cancel()

    def cleanup(self):
        """Cancel all active calls."""
        self.cancel_if_active(self.delay_call)

    def callback(self, result=None):
        """Make sure the timers are stopped when firing the callback."""
        self.cleanup()
        defer.Deferred.callback(self, result)

    def reset(self):
        """Reset the delay."""
        if not self.called:
            self.delay_call.reset(self.delay)

    @property
    def active(self):
        """Is the delay still active."""
        return self.delay_call.active()


class DeadlineTimer(Timer):
    """A Timer with a deadline."""

    def __init__(self, delay, timeout=None, clock=reactor):
        """Initialize this instance."""
        Timer.__init__(self, delay, clock)
        self.timeout = timeout
        self.timeout_call = self.clock.callLater(timeout, self.callback)

    def cleanup(self):
        """Cancel all active calls."""
        Timer.cleanup(self)
        self.cancel_if_active(self.timeout_call)


class FileDiscoveryBaseState(object):
    """States for file discovery bubble."""

    def __init__(self, bubble):
        """Initialize this instance."""
        self.bubble = bubble
        self.clock = bubble.clock

    def new_file_found(self):
        """New files found."""

    def cleanup(self):
        """Cleanup this instance."""


class FileDiscoveryIdleState(FileDiscoveryBaseState):
    """Waiting for first file to appear."""

    def new_file_found(self):
        """New files found."""
        self.bubble._start()


class FileDiscoveryGatheringState(FileDiscoveryBaseState):
    """Files are gathered then a notification is shown."""

    initial_delay = 0.5
    initial_timeout = 3.0

    def __init__(self, *args):
        """Initialize this instance."""
        super(FileDiscoveryGatheringState, self).__init__(*args)
        self.timer = DeadlineTimer(
            self.initial_delay, self.initial_timeout, clock=self.clock)
        self.timer.addCallback(self._timeout)

    def _timeout(self, result):
        """Show the notification bubble."""
        self.cleanup()
        self.bubble._popup()

    def new_file_found(self):
        """New files found."""
        self.timer.reset()

    def cleanup(self):
        """Cleanup this instance."""
        self.timer.cleanup()


class FileDiscoveryUpdateState(FileDiscoveryBaseState):
    """The bubble is updated if more files are found."""

    updates_delay = 0.5
    updates_timeout = 10.0

    def __init__(self, *args):
        """Initialize this instance."""
        super(FileDiscoveryUpdateState, self).__init__(*args)
        self.main_timer = Timer(self.updates_timeout, clock=self.clock)
        self.main_timer.addCallback(self._timeout)
        self.updates_timer = None

    def _timeout(self, result):
        """No more updates on the notification bubble."""
        self.cleanup()
        self.bubble.start_sleeping()

    def _update(self, result):
        """The bubble should be updated."""
        self.bubble._update()

    def new_file_found(self):
        """New files found."""
        if self.updates_timer is None:
            self.updates_timer = Timer(self.updates_delay, clock=self.clock)
            self.updates_timer.addCallback(self._update)

    def cleanup(self):
        """Clean up the timers."""
        self.main_timer.cleanup()
        if self.updates_timer:
            self.updates_timer.cleanup()


class FileDiscoverySleepState(FileDiscoveryBaseState):
    """The bubble is not updated while sleeping."""

    sleep_delay = 300.0

    def __init__(self, *args):
        """Initialize this instance."""
        super(FileDiscoverySleepState, self).__init__(*args)
        self.main_timer = Timer(self.sleep_delay, clock=self.clock)
        self.main_timer.addCallback(self._timeout)

    def _timeout(self, result):
        """Move the notification to the idle state."""
        self.bubble._set_idle()

    def cleanup(self):
        """Clean up the timers."""
        self.main_timer.cleanup()


class FileDiscoveryBubble(object):
    """
    Show a notification for file discovery.

    Waits 3 seconds for the file count to coalesce, then pops up a
    notification. If new files are found the notification is updated,
    but twice per second at most, and for up to 10 seconds.
    Finally, sleeps for 10 minutes so it does not get annoying.
    """

    state = None

    def __init__(self, status_aggregator, clock=reactor):
        """Initialize this instance."""
        self.connected = False
        self.files_found = False
        self.clock = clock
        self.status_aggregator = status_aggregator
        self._set_idle()
        self.notification = None

    def _change_state(self, new_state_class):
        """Change to a new state."""
        if self.state:
            self.state.cleanup()
        self.state = new_state_class(self)

    def _set_idle(self):
        """Reset this bubble to the initial state."""
        self._change_state(FileDiscoveryIdleState)

    def _start(self):
        """The first file was found, so start gathering."""
        self.notification = self.status_aggregator.get_notification()
        self._change_state(FileDiscoveryGatheringState)

    def _popup(self):
        """Display the notification."""
        if not self.connected:
            return
        text = self.status_aggregator.get_discovery_message()
        if text:
            self.notification.send_notification(UBUNTUONE_TITLE, text)
            logger.debug("notification shown: %s", text)
        self._change_state(FileDiscoveryUpdateState)

    def _update(self):
        """Update the notification."""
        if not self.connected:
            return
        text = self.status_aggregator.get_discovery_message()
        if text:
            logger.debug("notification updated: %s", text)
            self.notification.send_notification(UBUNTUONE_TITLE, text)

    def start_sleeping(self):
        """Wait for 10 minutes before annoying again."""
        self._change_state(FileDiscoverySleepState)

    def cleanup(self):
        """Cleanup this instance."""
        self.state.cleanup()

    def connection_made(self):
        """Connection made."""
        self.connected = True
        if self.files_found:
            self._popup()

    def connection_lost(self):
        """Connection lost."""
        self.connected = False

    def new_file_found(self):
        """New files found."""
        self.files_found = True
        self.state.new_file_found()


class ProgressBar(object):
    """Update a progressbar no more than 10 times a second."""
    pulsating = True
    visible = False
    progress = 0.0
    updates_delay = 0.1
    timer = None

    def __init__(self, clock=reactor):
        """Initialize this instance."""
        self.clock = clock
        try:
            self.launcher = UbuntuOneLauncher()
        except TypeError:
            # Unity GIR can cause a TypeError here so we should not fail
            self.launcher = DummyLauncher()

    def cleanup(self):
        """Cleanup this instance."""
        if self.timer:
            self.timer.cleanup()
            self.timer = None

    def _timeout(self, result):
        """The aggregating timer has expired, so update the UI."""
        self.timer = None
        self.launcher.set_progress(self.progress)
        logger.debug("progressbar updated: %f", self.progress)

    def set_progress(self, progress):
        """Steps amount changed. Set up a timer if there isn't one ticking."""
        self.progress = progress
        if not self.visible:
            self.visible = True
            self.launcher.show_progressbar()
            logger.debug("progressbar shown")
        if not self.timer:
            self.timer = Timer(self.updates_delay, clock=self.clock)
            self.timer.addCallback(self._timeout)

    def completed(self):
        """All has completed."""
        self.cleanup()
        self.visible = False
        self.launcher.hide_progressbar()
        logger.debug("progressbar hidden")


class FinalStatusBubble(object):
    """Final bubble that shows the status of transfers."""

    notification = None

    def __init__(self, status_aggregator):
        """Initialize this instance."""
        self.status_aggregator = status_aggregator

    def cleanup(self):
        """Clean up this instance."""

    def show(self):
        """Show the final status notification."""
        self.notification = self.status_aggregator.get_notification()
        text = self.status_aggregator.get_final_status_message()
        self.notification.send_notification(UBUNTUONE_TITLE, text)


def group_statuses(status_events):
    """Groups statuses by weight."""
    weight_getter = operator.attrgetter("WEIGHT")
    sorted_status_events = sorted(status_events, key=weight_getter)
    return itertools.groupby(sorted_status_events, weight_getter)


class StatusAggregator(object):
    """The status aggregator backend."""

    file_discovery_bubble = None
    final_status_bubble = None

    def __init__(self, clock=reactor):
        """Initialize this instance."""
        self.clock = clock
        self.notification_switch = NotificationSwitch()
        self.queue_done_timer = None
        self.reset()
        self.progress_bar = ProgressBar(clock=self.clock)
        self.finished_delay = 10
        self.progress = {}
        self.to_do = {}
        self.recent_transfers = deque(maxlen=5)
        self.connection_listeners = []
        self.progress_listeners = []

    def get_notification(self):
        """Create a new toggleable notification object."""
        return self.notification_switch.get_notification()

    def reset(self):
        """Reset all counters and notifications."""
        self.download_done = 0
        self.upload_done = 0
        self.files_uploading = []
        self.uploading_filename = ''
        self.files_downloading = []
        self.downloading_filename = ''
        if self.queue_done_timer is not None:
            self.queue_done_timer.cleanup()
            self.queue_done_timer = None

        if self.file_discovery_bubble:
            self.file_discovery_bubble.cleanup()
        self.file_discovery_bubble = FileDiscoveryBubble(self,
                                                         clock=self.clock)

        if self.final_status_bubble:
            self.final_status_bubble.cleanup()
        self.final_status_bubble = FinalStatusBubble(self)
        self.progress = {}
        self.to_do = {}

    def register_progress_listener(self, listener):
        """Register a callable object to be notified."""
        if isinstance(listener, Callable):
            self.progress_listeners.append(listener)
        else:
            raise TypeError("Callable object expected.")

    def register_connection_listener(self, listener):
        """Register a callable object to be notified."""
        if isinstance(listener, Callable):
            self.connection_listeners.append(listener)
        else:
            raise TypeError("Callable object expected.")

    def get_discovery_message(self):
        """Get the text for the discovery bubble."""
        lines = []
        files_uploading = len(self.files_uploading)
        if files_uploading > 0:
            self.uploading_filename = os.path.basename(
                self.files_uploading[0].path)
            lines.append(files_being_uploaded(
                self.uploading_filename, files_uploading))
        files_downloading = len(self.files_downloading)
        if files_downloading > 0:
            self.downloading_filename = os.path.basename(
                self.files_downloading[0].path)
            lines.append(files_being_downloaded(
                self.downloading_filename, files_downloading))
        return "\n".join(lines)

    def get_final_status_message(self):
        """Get some lines describing all we did."""
        parts = []
        parts.append(FINAL_COMPLETED)
        upload_done = self.upload_done
        if upload_done:
            parts.append(files_were_uploaded(
                self.uploading_filename, upload_done))

        download_done = self.download_done
        if download_done:
            parts.append(files_were_downloaded(
                self.downloading_filename, download_done))
        return "\n".join(parts)

    def _queue_done(self, _):
        """Show final bubble and reset counters."""
        self.queue_done_timer.cleanup()
        self.queue_done_timer = None
        logger.debug("queue done callback fired")
        if self.upload_done + self.download_done > 0:
            self.final_status_bubble.show()
        self.progress_bar.completed()
        self.reset()

    def queue_done(self):
        """Queue is finished."""
        if not self.to_do:
            return
        if self.queue_done_timer is None:
            logger.debug("queue done callback added")
            self.queue_done_timer = Timer(
                self.finished_delay, clock=self.clock)
            self.queue_done_timer.addCallback(self._queue_done)
            return
        logger.debug("queue done callback reset")
        self.queue_done_timer.reset()

    def update_progressbar(self):
        """Update the counters of the progressbar."""
        if len(self.to_do) > 0:
            progress = float(
                sum(self.progress.values())) / sum(self.to_do.values())
            self.progress_bar.set_progress(progress)
        for listener in self.progress_listeners:
            listener()

    def download_started(self, command):
        """A download just started."""
        if self.queue_done_timer is not None:
            self.queue_done_timer.cleanup()
            self.queue_done_timer = None
        self.files_downloading.append(command)
        if command.deflated_size is not None:
            self.to_do[
                (command.share_id, command.node_id)] = command.deflated_size
        if not self.downloading_filename:
            self.downloading_filename = os.path.basename(
                self.files_downloading[0].path)
        self.update_progressbar()
        logger.debug(
            "queueing command (total: %d): %s",
            len(self.to_do), command.__class__.__name__)
        self.file_discovery_bubble.new_file_found()

    def download_finished(self, command):
        """A download just finished."""
        if command in self.files_downloading:
            self.files_downloading.remove(command)
        self.download_done += 1
        if command.deflated_size is not None:
            self.progress[
                (command.share_id, command.node_id)] = command.deflated_size
        if command.path in self.recent_transfers:
            self.recent_transfers.remove(command.path)
        self.recent_transfers.append(command.path)
        logger.debug("unqueueing command: %s", command.__class__.__name__)
        self.update_progressbar()

    def upload_started(self, command):
        """An upload just started."""
        if self.queue_done_timer is not None:
            self.queue_done_timer.cleanup()
            self.queue_done_timer = None
        self.files_uploading.append(command)
        if command.deflated_size is not None:
            self.to_do[
                (command.share_id, command.node_id)] = command.deflated_size
        if not self.uploading_filename:
            self.uploading_filename = os.path.basename(
                self.files_uploading[0].path)
        self.update_progressbar()
        logger.debug(
            "queueing command (total: %d): %s", len(self.to_do),
            command.__class__.__name__)
        self.file_discovery_bubble.new_file_found()

    def upload_finished(self, command):
        """An upload just finished."""
        if command in self.files_uploading:
            self.files_uploading.remove(command)
        self.upload_done += 1
        if command.deflated_size is not None:
            self.progress[
                (command.share_id, command.node_id)] = command.deflated_size
        if command.path in self.recent_transfers:
            self.recent_transfers.remove(command.path)
        self.recent_transfers.append(command.path)
        logger.debug("unqueueing command: %s", command.__class__.__name__)
        self.update_progressbar()

    def progress_made(self, share_id, node_id, n_bytes, deflated_size):
        """Progress made on up- or download."""
        if n_bytes is not None:
            # if we haven't gotten the total size yet, set it now
            if deflated_size and (share_id, node_id) not in self.to_do:
                self.to_do[(share_id, node_id)] = deflated_size
            self.progress[(share_id, node_id)] = n_bytes
        self.update_progressbar()

    def connection_lost(self):
        """The connection to the server was lost."""
        self.file_discovery_bubble.connection_lost()
        for callback in self.connection_listeners:
            callback(False)

    def connection_made(self):
        """The connection to the server was made."""
        self.file_discovery_bubble.connection_made()
        for callback in self.connection_listeners:
            callback(True)


class StatusFrontend(object):
    """Frontend for the status aggregator, used by the StatusListener."""

    def __init__(self, clock=reactor, service=None):
        """Initialize this instance."""
        self.aggregator = StatusAggregator(clock=clock)
        self.notification = self.aggregator.get_notification()
        self.quota_timer = None

        self.syncdaemon_service = service
        self.sync_menu = None
        self.start_sync_menu()
        self.farewell_ubuntuone_sync()

    def farewell_ubuntuone_sync(self):
        """Show notification about the upcoming end of UbuntuOne sync."""
        self.notification.send_notification(
            UBUNTUONE_TITLE, UBUNTUONE_END)

    def start_sync_menu(self):
        """Create the sync menu and register the progress listener."""
        if self.syncdaemon_service is not None:
            self.sync_menu = sync_menu.UbuntuOneSyncMenu(
                self, self.syncdaemon_service)
            self.aggregator.register_connection_listener(
                self.sync_menu.sync_status_changed)
            self.aggregator.register_progress_listener(
                self.sync_menu.update_transfers)

    def recent_transfers(self):
        """Return a list of paths of recently transferred files."""
        return list(self.aggregator.recent_transfers)

    def files_uploading(self):
        """Return list with (path, size, written) per current upload."""
        uploading = []
        for upload in self.aggregator.files_uploading:
            if upload.deflated_size not in (0, None):
                uploading.append(
                    (upload.path, upload.deflated_size, upload.n_bytes_written)
                )
        return uploading

    def files_downloading(self):
        """Returns list with (path, size, read) per current download."""
        downloading = []
        for download in self.aggregator.files_downloading:
            if download.deflated_size not in (0, None):
                downloading.append((download.path, download.deflated_size,
                                    download.n_bytes_read))
        return downloading

    def file_published(self, public_url):
        """A file was published."""
        status_event = FilePublishingStatus(new_public_url=public_url)
        self.notification.send_notification(
            UBUNTUONE_TITLE, status_event.one())

    def file_unpublished(self, public_url):
        """A file was unpublished."""
        self.notification.send_notification(
            UBUNTUONE_TITLE, FileUnpublishingStatus().one())

    def download_started(self, command):
        """A file was queued for download."""
        self.aggregator.download_started(command)

    def download_finished(self, command):
        """A file download was unqueued."""
        self.aggregator.download_finished(command)

    def upload_started(self, command):
        """A file was queued for upload."""
        self.aggregator.upload_started(command)

    def upload_finished(self, command):
        """A file upload was unqueued."""
        self.aggregator.upload_finished(command)

    def progress_made(self, share_id, node_id, n_bytes, deflated_size):
        """Progress made on up- or download."""
        self.aggregator.progress_made(
            share_id, node_id, n_bytes, deflated_size)

    def queue_done(self):
        """The queue is empty."""
        self.aggregator.queue_done()

    def new_share_available(self, share):
        """A new share is available for subscription."""
        self.notification.send_notification(
            UBUNTUONE_TITLE, ShareAvailableStatus(share=share).one())

    def new_udf_available(self, udf):
        """A new udf is available for subscription."""
        if udf.subscribed:
            return
        self.notification.send_notification(
            UBUNTUONE_TITLE, UDFAvailableStatus(udf=udf).one())

    def server_connection_lost(self):
        """The client lost the connection to the server."""
        logger.debug("server connection lost")
        self.aggregator.connection_lost()

    def server_connection_made(self):
        """The client made the connection to the server."""
        logger.debug("server connection made")
        self.aggregator.connection_made()

    def udf_quota_exceeded(self, volume_dict):
        """Quota exceeded in UDF."""
        logger.debug("UDF quota exceeded for volume %r." % volume_dict)
        alert_user()

    def share_quota_exceeded(self, volume_dict):
        """Sharing user's quota exceeded in share."""
        logger.debug("Share quota exceeded for volume %r." % volume_dict)
        if self.quota_timer is not None:
            if self.quota_timer.active:
                return
        else:
            self.quota_timer = Timer(ONE_DAY, clock=self.aggregator.clock)
        self.notification.send_notification(
            UBUNTUONE_TITLE, SHARE_QUOTA_EXCEEDED % (
                volume_dict['path'], volume_dict['other_visible_name']))
        alert_user()

    def root_quota_exceeded(self, volume_dict):
        """Quota exceeded in root."""
        logger.debug("Root quota exceeded for volume %r." % volume_dict)
        alert_user()

    def set_show_all_notifications(self, value):
        """Set the flag to show all notifications."""
        if value:
            self.aggregator.notification_switch.enable_notifications()
        else:
            self.aggregator.notification_switch.disable_notifications()
