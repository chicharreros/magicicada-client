# tests.status.test_aggregator
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
"""Tests for the status events aggregator."""

import logging

from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase
from mocker import Mocker

from contrib.testing.testcase import BaseTwistedTestCase
from ubuntuone.devtools.handlers import MementoHandler
from ubuntuone.devtools.testcases import skipTest
from ubuntuone.status import aggregator
from ubuntuone.status.notification import AbstractNotification
from ubuntuone.syncdaemon import (
    status_listener,
    RECENT_TRANSFERS,
    UPLOADING,
    DOWNLOADING
)
from ubuntuone.syncdaemon.volume_manager import Share, UDF, Root

FILENAME = 'example.txt'
FILENAME2 = 'another_example.mp3'


class PatchedClock(Clock):
    """Patch the clock to fix twisted bug #4823."""

    def advance(self, amount):
        """Sort the calls before advancing the clock."""
        self.calls.sort(lambda a, b: cmp(a.getTime(), b.getTime()))
        Clock.advance(self, amount)


class TimerTestCase(TestCase):
    """Test the Timer class."""

    TIMEOUT = 3.0

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(TimerTestCase, self).setUp()
        self.clock = PatchedClock()
        self.timer = aggregator.Timer(delay=3.0, clock=self.clock)

    def test_not_fired_initially(self):
        """The timer is not fired initially"""
        self.assertFalse(self.timer.called)

    def test_fired_after_delay(self):
        """The timer is fired after the initial delay."""
        self.clock.advance(self.timer.delay)
        self.assertTrue(self.timer.called)

    def test_cleanup_cancels_delay_call(self):
        """Calling cleanup cancels the delay call."""
        self.timer.cleanup()
        self.assertTrue(self.timer.delay_call.cancelled)

    def test_not_fired_immediately(self):
        """The timer is not fired immediately."""
        self.timer.reset()
        self.assertFalse(self.timer.called)

    def test_fired_after_initial_wait(self):
        """The timer is fired after an initial wait."""
        self.timer.reset()
        self.clock.advance(self.timer.delay)
        self.assertTrue(self.timer.called)

    def test_not_fired_if_reset_within_delay(self):
        """The timer is not fired if it is reset within the delay."""
        self.timer.reset()
        self.clock.advance(self.timer.delay / 0.8)
        self.timer.reset()
        self.clock.advance(self.timer.delay / 0.8)
        self.assertTrue(self.timer.called)

    def test_active(self):
        """The timer is active until the delay is reached."""
        self.timer.reset()
        self.assertTrue(self.timer.active)
        self.clock.advance(self.timer.delay + 1)
        self.assertFalse(self.timer.active)


class DeadlineTimerTestCase(TimerTestCase):
    """Test the DeadlineTimer class."""

    DELAY = 0.5

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(DeadlineTimerTestCase, self).setUp()
        self.clock = PatchedClock()
        self.timer = aggregator.DeadlineTimer(
            delay=0.5, timeout=3.0, clock=self.clock)

    def test_fired_if_initial_timeout_exceeded(self):
        """Timer is fired if the initial timeout is exceeded."""
        small_delay = self.timer.delay * 0.8
        for n in range(int(self.timer.timeout / small_delay) + 1):
            self.timer.reset()
            self.clock.advance(small_delay)
        self.assertTrue(self.timer.called)

    def test_not_fired_twice_if_delay_exceeded(self):
        """Timer is not fired twice if the delay is exceeded."""
        large_delay = self.timer.delay * 1.2
        for n in range(int(self.timer.timeout / large_delay) + 1):
            self.timer.reset()
            self.clock.advance(large_delay)
        self.clock.advance(self.timer.delay)
        self.assertTrue(self.timer.called)

    def test_not_fired_twice_if_timeout_exceeded(self):
        """Timer is not fired twice if the timeout is exceeded."""
        small_delay = self.timer.delay * 0.8
        for n in range(int(self.timer.timeout / small_delay) + 1):
            self.timer.reset()
            self.clock.advance(small_delay)
        self.clock.advance(self.timer.delay)
        self.assertTrue(self.timer.called)

    def test_cleanup_cancels_timeout_call(self):
        """Calling cleanup cancels the delay call."""
        self.timer.cleanup()
        self.assertTrue(self.timer.timeout_call.cancelled)


class FakeNotification(AbstractNotification):
    """A fake notification class."""

    def __init__(self, application_name="fake app"):
        """Initialize this instance."""
        self.notifications_shown = []
        self.notification_switch = None
        self.application_name = application_name
        self.notification = None

    def send_notification(self, title, message, icon=None, append=False):
        """Show a notification to the user."""
        if (self.notification_switch is not None and
                not self.notification_switch.enabled):
            return
        self.notification = (title, message, icon, append)
        self.notifications_shown.append((title, message, icon, append))
        return len(self.notifications_shown) - 1


def FakeNotificationSingleton():
    """Builds a notification singleton, that logs all notifications shown."""
    instance = FakeNotification()

    def get_instance(notification_switch):
        """Returns the single instance."""
        instance.notification_switch = notification_switch
        return instance

    return get_instance


class FakeStatusAggregator(object):
    """A fake status aggregator."""

    def __init__(self, clock):
        """Initialize this instance."""
        self.discovered = 0
        self.completed = 0
        self.notification_switch = aggregator.NotificationSwitch()

    def get_discovery_message(self):
        """Return the file discovery message."""
        self.discovered += 1
        return self.build_discovery_message()

    def build_discovery_message(self):
        """Build the file discovery message."""
        return "a lot of files found (%d)." % self.discovered

    def get_progress_message(self):
        """Return the progress message."""
        self.completed += 1
        return self.build_progress_message()

    def build_progress_message(self):
        """Build the progress message."""
        params = (self.discovered, self.completed)
        return "a lot of files transferring (%d/%d)." % params

    def get_final_status_message(self):
        """Return the final status message."""
        return "a lot of files completed."

    def get_notification(self):
        """Create a new toggleable notification object."""
        return self.notification_switch.get_notification()


class ToggleableNotificationTestCase(TestCase):
    """Test the ToggleableNotification class."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(ToggleableNotificationTestCase, self).setUp()
        self.patch(aggregator.notification, "Notification", FakeNotification)
        self.notification_switch = aggregator.NotificationSwitch()
        self.toggleable = self.notification_switch.get_notification()

    def assertShown(self, notification):
        """Assert that the notification was shown."""
        self.assertIn(notification,
                      self.toggleable.notification.notifications_shown)

    def assertNotShown(self, notification):
        """Assert that the notification was shown."""
        self.assertNotIn(notification,
                         self.toggleable.notification.notifications_shown)

    def test_send_notification_passes_thru(self):
        """The send_notification method passes thru."""
        args = (1, 2, 3, 4)
        self.toggleable.send_notification(*args)
        self.assertShown(args)

    def test_send_notification_honored_when_enabled(self):
        """The send_notification method is honored when enabled."""
        self.notification_switch.enable_notifications()
        args = (aggregator.NAME, "hello", None, False)
        self.toggleable.send_notification(*args)
        self.assertShown(args)

    def test_send_notification_ignored_when_disabled(self):
        """The send_notification method is ignored when disabled."""
        self.notification_switch.disable_notifications()
        args = (aggregator.NAME, "hello", None, False)
        self.toggleable.send_notification(*args)
        self.assertNotShown(args)


class NotificationSwitchTestCase(TestCase):
    """Test the NotificationSwitch class."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(NotificationSwitchTestCase, self).setUp()
        self.notification_switch = aggregator.NotificationSwitch()

    def test_get_notification(self):
        """A new notification instance is returned."""
        notification = self.notification_switch.get_notification()
        self.assertEqual(notification.notification_switch,
                         self.notification_switch)

    def test_enable_notifications(self):
        """The switch is turned on."""
        self.notification_switch.enable_notifications()
        self.assertTrue(self.notification_switch.enabled)

    def test_disable_notifications(self):
        """The switch is turned off."""
        self.notification_switch.disable_notifications()
        self.assertFalse(self.notification_switch.enabled)


class FileDiscoveryBubbleTestCase(TestCase):
    """Test the FileDiscoveryBubble class."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(FileDiscoveryBubbleTestCase, self).setUp()
        self.patch(aggregator, "ToggleableNotification",
                   FakeNotificationSingleton())
        self.clock = PatchedClock()
        self.aggregator = FakeStatusAggregator(clock=self.clock)
        self.bubble = aggregator.FileDiscoveryBubble(self.aggregator,
                                                     clock=self.clock)
        self.addCleanup(self.bubble.cleanup)
        fdis = aggregator.FileDiscoveryGatheringState
        self.initial_delay = fdis.initial_delay
        self.smaller_delay = self.initial_delay * 0.8
        self.initial_timeout = fdis.initial_timeout
        fdus = aggregator.FileDiscoveryUpdateState
        self.updates_delay = fdus.updates_delay
        self.updates_timeout = fdus.updates_timeout
        fdss = aggregator.FileDiscoverySleepState
        self.sleep_delay = fdss.sleep_delay

        self.handler = MementoHandler()
        self.handler.setLevel(logging.DEBUG)
        aggregator.logger.addHandler(self.handler)
        aggregator.logger.setLevel(logging.DEBUG)
        self.addCleanup(aggregator.logger.removeHandler, self.handler)

    def get_notifications_shown(self):
        """The list of notifications shown."""
        return self.bubble.notification.notifications_shown

    def test_popup_shows_notification_when_connected(self):
        """The popup callback shows notifications."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.bubble._popup()
        message = self.aggregator.build_discovery_message()
        notification = (aggregator.NAME, message, None, False)
        self.assertIn(notification, self.get_notifications_shown())

    def test_popup_shows_notification_after_connected(self):
        """The popup callback shows notifications."""
        self.bubble.new_file_found()
        self.bubble.connection_made()
        message = self.aggregator.build_discovery_message()
        notification = (aggregator.NAME, message, None, False)
        self.assertIn(notification, self.get_notifications_shown())

    def test_popup_shows_no_notification_before_connection_made(self):
        """The popup callback shows notifications."""
        self.bubble.new_file_found()
        self.bubble._popup()
        message = self.aggregator.build_discovery_message()
        notification = (aggregator.NAME, message, None, False)
        self.assertNotIn(notification, self.get_notifications_shown())

    def test_popup_shows_no_notification_after_connection_lost(self):
        """The popup callback shows notifications."""
        self.bubble.connection_made()
        self.bubble.connection_lost()
        self.bubble.new_file_found()
        self.bubble._popup()
        message = self.aggregator.build_discovery_message()
        notification = (aggregator.NAME, message, None, False)
        self.assertNotIn(notification, self.get_notifications_shown())

    def test_notification_is_logged_in_debug(self):
        """The notification is printed in the debug log."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.bubble._popup()
        msg = "notification shown: %s" % self.get_notifications_shown()[0][1]
        self.assertTrue(self.handler.check_debug(msg))

    def test_bubble_is_not_shown_initially(self):
        """The bubble is not shown initially."""
        self.bubble.new_file_found()
        self.assertEqual(0, len(self.get_notifications_shown()))

    def test_bubble_is_shown_after_delay(self):
        """The bubble is shown after a delay."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.clock.advance(self.initial_delay)
        self.assertEqual(1, len(self.get_notifications_shown()))

    def test_bubble_not_shown_if_more_files_found(self):
        """The bubble is not shown if more files found within delay."""
        self.clock.advance(self.smaller_delay)
        self.bubble.new_file_found()
        self.clock.advance(self.smaller_delay)
        self.assertEqual(0, len(self.get_notifications_shown()))

    def test_bubble_shown_if_timeout_exceeded(self):
        """The bubble is shown if the timeout is exceeded."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        count = int(self.initial_timeout / self.smaller_delay) + 1
        for n in range(count):
            self.clock.advance(self.smaller_delay)
            self.bubble.new_file_found()
        self.assertEqual(1, len(self.get_notifications_shown()))

    def test_idle_state(self):
        """The idle state is verified."""
        self.assertEqual(
            type(self.bubble.state), aggregator.FileDiscoveryIdleState)

    def test_gathering_state(self):
        """The gathering state is set after the first file is found."""
        self.bubble.new_file_found()
        self.assertEqual(
            type(self.bubble.state), aggregator.FileDiscoveryGatheringState)

    def test_update_state(self):
        """When the gathering state finishes, the update state is started."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.clock.advance(self.initial_delay)
        self.assertEqual(
            type(self.bubble.state), aggregator.FileDiscoveryUpdateState)

    def test_sleeping_state(self):
        """When the update state finishes, the sleeping state is started."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.clock.advance(self.initial_delay)
        self.clock.advance(self.updates_timeout)
        self.assertEqual(
            type(self.bubble.state), aggregator.FileDiscoverySleepState)

    def test_back_to_initial_state(self):
        """When the last state finishes, we return to the idle state."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.clock.advance(self.initial_delay)
        self.clock.advance(self.updates_timeout)
        self.clock.advance(self.sleep_delay)
        self.assertEqual(
            type(self.bubble.state), aggregator.FileDiscoveryIdleState)

    def test_new_files_found_while_updating_not_shown_immediately(self):
        """New files found in the updating state are not shown immediately."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.clock.advance(self.initial_delay)
        self.bubble.new_file_found()
        self.assertEqual(1, len(self.get_notifications_shown()))

    def test_new_files_found_while_updating_are_shown_after_a_delay(self):
        """New files found in the updating state are shown after a delay."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.clock.advance(self.initial_delay)
        self.bubble.new_file_found()
        self.clock.advance(self.updates_delay)
        self.assertEqual(2, len(self.get_notifications_shown()))

    def test_update_modifies_notification(self):
        """The update callback updates notifications."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.bubble._popup()
        self.bubble.new_file_found()
        self.bubble._update()
        message = self.aggregator.build_discovery_message()
        notification = (aggregator.NAME, message, None, False)
        self.assertIn(notification, self.get_notifications_shown())

    def test_update_is_logged_in_debug(self):
        """The notification is logged when _update is called."""
        self.bubble.connection_made()
        self.bubble.new_file_found()
        self.bubble._popup()
        self.bubble.new_file_found()
        self.bubble._update()
        msg = "notification updated: %s" % self.get_notifications_shown()[1][1]
        self.assertTrue(self.handler.check_debug(msg))


class FinalBubbleTestCase(TestCase):
    """Test for the final status notification bubble."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(FinalBubbleTestCase, self).setUp()
        self.patch(aggregator, "ToggleableNotification",
                   FakeNotificationSingleton())
        self.clock = PatchedClock()
        self.aggregator = FakeStatusAggregator(clock=self.clock)
        self.bubble = aggregator.FinalStatusBubble(self.aggregator)
        self.addCleanup(self.bubble.cleanup)

    def test_notification_not_shown_initially(self):
        """The notification is not shown initially."""
        self.assertEqual(None, self.bubble.notification)

    def test_show_pops_bubble(self):
        """The show method pops the bubble immediately."""
        self.bubble.show()
        self.assertEqual(1, len(self.bubble.notification.notifications_shown))


class FakeLauncher(object):
    """A fake Launcher."""

    progress_visible = False
    progress = 0.0

    def show_progressbar(self):
        """The progressbar is shown."""
        self.progress_visible = True

    def hide_progressbar(self):
        """The progressbar is hidden."""
        self.progress_visible = False

    def set_progress(self, value):
        """The progressbar value is changed."""
        self.progress = value


class FakeInhibitor(object):
    """A fake session inhibitor."""

    def inhibit(self, flags, reason):
        """Inhibit some events with a given reason."""
        self.flags = flags
        return defer.succeed(self)

    def cancel(self):
        """Cancel the inhibition for the current cookie."""
        self.flags = 0
        return defer.succeed(self)


class ProgressBarTestCase(TestCase):
    """Tests for the progress bar."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(ProgressBarTestCase, self).setUp()
        self.patch(aggregator, "Launcher", FakeLauncher)
        self.clock = PatchedClock()
        self.bar = aggregator.ProgressBar(clock=self.clock)
        self.addCleanup(self.bar.cleanup)
        self.timeout_calls = []
        original_timeout = self.bar._timeout

        def fake_timeout(result):
            """A fake _timeout method."""
            self.timeout_calls.append(self.bar.progress)
            original_timeout(result)

        self.patch(self.bar, "_timeout", fake_timeout)

    def test_launcher_typeerror_nonfatal(self):
        """Test that Launcher raising TypeError is not fatal."""
        def raise_typeerror(*args, **kwargs):
            raise TypeError

        self.patch(aggregator, "Launcher", raise_typeerror)
        aggregator.ProgressBar(clock=self.clock)

    def test_shown_when_progress_made(self):
        """The progress bar is shown when progress is made."""
        self.bar.set_progress(0.5)
        self.assertTrue(self.bar.visible)
        self.assertTrue(self.bar.launcher.progress_visible)

    def test_progress_made_updates_counter(self):
        """Progress made updates the counter."""
        self.bar.set_progress(0.5)
        self.assertEqual(self.bar.progress, 0.5)

    def test_no_timer_set_initially(self):
        """There's no timer set initially."""
        self.assertEqual(self.bar.timer, None)

    def test_progress_made_sets_timer(self):
        """Progress made sets up a timer."""
        self.bar.set_progress(0.5)
        self.assertNotEqual(self.bar.timer, None)

    def test_cleanup_resets_timer(self):
        """The cleanup method resets the timer."""
        self.bar.set_progress(0.5)
        self.bar.cleanup()
        self.assertEqual(self.bar.timer, None)

    def test_progress_made_not_updated_initially(self):
        """Progress made is not updated initially."""
        self.bar.set_progress(0.5)
        self.assertEqual(0, len(self.timeout_calls))
        self.assertEqual(0.0, self.bar.launcher.progress)

    def test_progress_made_updated_after_a_delay(self):
        """The progressbar is updated after a delay."""
        self.bar.set_progress(0.5)
        self.clock.advance(aggregator.ProgressBar.updates_delay)
        self.assertIn(0.5, self.timeout_calls)
        self.assertEqual(0.5, self.bar.launcher.progress)

    def test_progress_updates_are_aggregated(self):
        """The progressbar is updated after a delay."""
        self.bar.set_progress(0.5)
        self.clock.advance(aggregator.ProgressBar.updates_delay / 2)
        self.bar.set_progress(0.6)
        self.clock.advance(aggregator.ProgressBar.updates_delay / 2)
        self.assertEqual(1, len(self.timeout_calls))

    def test_progress_updates_are_continuous(self):
        """The progressbar updates are continuous."""
        self.bar.set_progress(0.5)
        self.clock.advance(aggregator.ProgressBar.updates_delay)
        self.assertEqual(0.5, self.bar.launcher.progress)
        self.bar.set_progress(0.6)
        self.clock.advance(aggregator.ProgressBar.updates_delay)
        self.assertEqual(0.6, self.bar.launcher.progress)
        self.assertEqual(2, len(self.timeout_calls))

    def test_hidden_when_completed(self):
        """The progressbar is hidden when everything completes."""
        self.bar.set_progress(0.5)
        self.bar.completed()
        self.assertFalse(self.bar.visible)
        self.assertFalse(self.bar.launcher.progress_visible)

    @skipTest('Inhibitor is disabled to prevent bug #737620')
    @defer.inlineCallbacks
    def test_progress_made_inhibits_logout_suspend(self):
        """Suspend and logout are inhibited when the progressbar is shown."""
        self.bar.set_progress(0.5)
        expected = aggregator.session.INHIBIT_LOGOUT_SUSPEND
        inhibitor = yield self.bar.inhibitor_defer
        self.assertEqual(inhibitor.flags, expected)

    @skipTest('Inhibitor is disabled to prevent bug #737620')
    @defer.inlineCallbacks
    def test_completed_uninhibits_logout_suspend(self):
        """Suspend and logout are uninhibited when all has completed."""
        self.bar.set_progress(0.5)
        d = self.bar.inhibitor_defer
        self.bar.completed()
        inhibitor = yield d
        self.assertEqual(inhibitor.flags, 0)


class FakeDelayedBuffer(object):
    """Appends all status pushed into a list."""
    timer_reset = False
    processed = False

    def __init__(self, *args, **kwargs):
        """Initialize this instance."""
        self.events = []

    def push_event(self, event):
        """Push an event into this buffer."""
        self.events.append(event)

    def reset_threshold_timer(self):
        """The status has changed."""
        self.timer_reset = True

    def process_accumulated(self):
        """Process accumulated events."""
        self.processed = True


class FakeCommand(object):
    """A fake command."""

    def __init__(self, path=''):
        self.path = path
        self.share_id = path
        self.node_id = path
        self.deflated_size = 10000
        self.size = 0


class FakeUploadCommand(FakeCommand):
    """A fake upload."""
    def __init__(self, path=''):
        super(FakeUploadCommand, self).__init__(path)
        self.n_bytes_written = 0


class FakeDownloadCommand(FakeCommand):
    """A fake upload."""
    def __init__(self, path=''):
        super(FakeDownloadCommand, self).__init__(path)
        self.n_bytes_read = 0


class FakeVolumeManager(object):
    """A fake vm."""

    def __init__(self):
        """Initialize this instance."""
        self.volumes = {}
        self.root = None

    def get_volume(self, volume_id):
        """Return a volume given its id."""
        return self.volumes[volume_id]


class FakeAggregator(object):
    """A fake aggregator object."""

    def __init__(self, clock):
        """Initialize this fake instance."""
        self.queued_commands = set()
        self.notification_switch = aggregator.NotificationSwitch()
        self.connected = False
        self.clock = PatchedClock()
        self.files_uploading = []
        self.files_downloading = []
        self.progress_events = []
        self.recent_transfers = aggregator.deque(maxlen=10)

    def queue_done(self):
        """The queue completed all operations."""
        self.queued_commands.clear()

    def get_notification(self):
        """Create a new toggleable notification object."""
        return self.notification_switch.get_notification()

    def download_started(self, command):
        """A download just started."""
        self.files_downloading.append(command)
        self.queued_commands.add(command)

    def download_finished(self, command):
        """A download just finished."""
        if command in self.files_downloading:
            self.files_downloading.remove(command)
        self.recent_transfers.append(command.path)
        self.queued_commands.discard(command)

    def upload_started(self, command):
        """An upload just started."""
        self.files_uploading.append(command)
        self.queued_commands.add(command)

    def upload_finished(self, command):
        """An upload just finished."""
        if command in self.files_uploading:
            self.files_uploading.remove(command)
        self.recent_transfers.append(command.path)
        self.queued_commands.discard(command)

    def progress_made(self, share_id, node_id, n_bytes, deflated_size):
        """Progress made on up- or download."""
        self.progress_events.append(
            (share_id, node_id, n_bytes, deflated_size))

    def connection_made(self):
        """The client made the connection to the server."""
        self.connected = True

    def connection_lost(self):
        """The client lost the connection to the server."""
        self.connected = False


class StatusFrontendTestCase(BaseTwistedTestCase):
    """Test the status frontend."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(StatusFrontendTestCase, self).setUp()
        self.patch(aggregator, "StatusAggregator", FakeAggregator)
        self.patch(aggregator, "ToggleableNotification",
                   FakeNotificationSingleton())
        self.fakefsm = None
        self.fakevm = FakeVolumeManager()
        self.status_frontend = aggregator.StatusFrontend()
        self.listener = status_listener.StatusListener(self.fakefsm,
                                                       self.fakevm,
                                                       self.status_frontend)

    def test_recent_transfers(self):
        """Check that it generates a tuple with the recent transfers."""
        self.patch(status_listener.action_queue, "Upload", FakeUploadCommand)
        self.patch(status_listener.action_queue, "Download",
                   FakeDownloadCommand)

        fake_command = FakeUploadCommand('path1')
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        self.listener.handle_SYS_QUEUE_REMOVED(fake_command)
        fake_command = FakeUploadCommand('path2')
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        self.listener.handle_SYS_QUEUE_REMOVED(fake_command)
        fake_command = FakeDownloadCommand('path3')
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        self.listener.handle_SYS_QUEUE_REMOVED(fake_command)
        transfers = self.status_frontend.recent_transfers()
        expected = ['path1', 'path2', 'path3']
        self.assertEqual(transfers, expected)

        menu_data = self.listener.menu_data()
        self.assertEqual(
            menu_data,
            {UPLOADING: [],
             DOWNLOADING: [],
             RECENT_TRANSFERS: expected})

    def test_files_uploading(self):
        """Check that it returns a list with the path, size, and progress."""
        fc = FakeUploadCommand(path='testfile.txt')
        fc.deflated_size = 200
        self.status_frontend.upload_started(fc)
        uploading = self.status_frontend.files_uploading()
        expected = [('testfile.txt', 200, 0)]
        self.assertEqual(uploading, expected)
        menu_data = self.listener.menu_data()
        self.assertEqual(
            menu_data,
            {UPLOADING: expected,
             DOWNLOADING: [],
             RECENT_TRANSFERS: []})

        fc.deflated_size = 1000
        fc.n_bytes_written = 200
        fc2 = FakeUploadCommand(path='testfile2.txt')
        fc2.deflated_size = 2000
        fc2.n_bytes_written = 450
        self.status_frontend.upload_started(fc2)
        uploading = self.status_frontend.files_uploading()
        expected = [('testfile.txt', 1000, 200), ('testfile2.txt', 2000, 450)]
        self.assertEqual(uploading, expected)

        menu_data = self.listener.menu_data()
        self.assertEqual(
            menu_data,
            {UPLOADING: expected,
             DOWNLOADING: [],
             RECENT_TRANSFERS: []})

    def test_files_downloading(self):
        """Check that it returns a list with the path, size, and progress."""
        fc = FakeDownloadCommand(path='testfile.txt')
        fc.deflated_size = 200
        self.status_frontend.download_started(fc)
        downloading = self.status_frontend.files_downloading()
        expected = [('testfile.txt', 200, 0)]
        self.assertEqual(downloading, expected)
        menu_data = self.listener.menu_data()
        self.assertEqual(
            menu_data,
            {DOWNLOADING: expected,
             UPLOADING: [],
             RECENT_TRANSFERS: []})

        fc.deflated_size = 1000
        fc.n_bytes_read = 200
        fc2 = FakeDownloadCommand(path='testfile2.txt')
        fc2.deflated_size = 2000
        fc2.n_bytes_read = 450
        self.status_frontend.download_started(fc2)
        downloading = self.status_frontend.files_downloading()
        expected = [('testfile.txt', 1000, 200), ('testfile2.txt', 2000, 450)]
        self.assertEqual(downloading, expected)

        menu_data = self.listener.menu_data()
        self.assertEqual(
            menu_data,
            {DOWNLOADING: expected,
             UPLOADING: [],
             RECENT_TRANSFERS: []})

    def test_files_uploading_empty(self):
        """Check that empty files are ignored."""
        fc = FakeUploadCommand(path='testfile.txt')
        fc.deflated_size = None
        self.status_frontend.upload_started(fc)

        fc2 = FakeUploadCommand(path='testfile2.txt')
        fc2.deflated_size = 0
        fc2.n_bytes_written = 450
        self.status_frontend.upload_started(fc2)
        uploading = self.status_frontend.files_uploading()
        self.assertEqual(uploading, [])

    def test_files_downloading_empty(self):
        """Check that empty files are ignored."""
        fc = FakeDownloadCommand(path='testfile.txt')
        fc.deflated_size = None
        self.status_frontend.download_started(fc)

        fc2 = FakeDownloadCommand(path='testfile2.txt')
        fc2.deflated_size = 0
        fc2.n_bytes_written = 450
        self.status_frontend.download_started(fc2)
        downloading = self.status_frontend.files_downloading()
        self.assertEqual(downloading, [])

    def test_menu_data_full_response(self):
        """listener.menu_data returns uploading, downloading, and recent."""
        self.patch(status_listener.action_queue, "Upload", FakeUploadCommand)
        fake_command = FakeUploadCommand('path1')
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        self.listener.handle_SYS_QUEUE_REMOVED(fake_command)

        self.patch(status_listener.action_queue, "Download",
                   FakeDownloadCommand)
        fake_command = FakeDownloadCommand('path2')
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        self.listener.handle_SYS_QUEUE_REMOVED(fake_command)

        fc = FakeUploadCommand(path='testfile.txt')
        fc.deflated_size = 1000
        fc.n_bytes_written = 200
        self.status_frontend.upload_started(fc)

        fc = FakeDownloadCommand(path='download.pdf')
        fc.deflated_size = 10
        fc.n_bytes_read = 1
        self.status_frontend.download_started(fc)

        uploading = self.status_frontend.files_uploading()
        downloading = self.status_frontend.files_downloading()
        transfers = self.status_frontend.recent_transfers()
        expected = {UPLOADING: [('testfile.txt', 1000, 200)],
                    DOWNLOADING: [('download.pdf', 10, 1)],
                    RECENT_TRANSFERS: ['path1', 'path2']}

        self.assertEqual({UPLOADING: uploading,
                          DOWNLOADING: downloading,
                          RECENT_TRANSFERS: transfers},
                         expected)

    def test_file_published(self):
        """A file published event is processed."""
        share_id = "fake share id"
        node_id = "fake node id"
        is_public = True
        public_url = "http://fake_public/url"
        self.listener.handle_AQ_CHANGE_PUBLIC_ACCESS_OK(share_id, node_id,
                                                        is_public, public_url)
        self.assertEqual(
            2, len(self.status_frontend.notification.notifications_shown))

    def test_file_unpublished(self):
        """A file unpublished event is processed."""
        share_id = "fake share id"
        node_id = "fake node id"
        is_public = False
        public_url = None  # SD sends None when unpublishing

        self.listener.handle_AQ_CHANGE_PUBLIC_ACCESS_OK(share_id, node_id,
                                                        is_public, public_url)
        self.assertEqual(
            2, len(self.status_frontend.notification.notifications_shown))

    def test_download_started(self):
        """A download was added to the queue."""
        self.patch(status_listener.action_queue, "Download", FakeCommand)
        fake_command = FakeCommand()
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        qc = self.status_frontend.aggregator.queued_commands
        self.assertIn(fake_command, qc)

    def test_download_started_with_no_deflated_size(self):
        """A download of unknown size was added to the queue."""
        self.patch(status_listener.action_queue, "Download", FakeCommand)
        fake_command = FakeCommand()
        fake_command.deflated_size = None
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        qc = self.status_frontend.aggregator.queued_commands
        self.assertIn(fake_command, qc)

    def test_download_finished(self):
        """A download was removed from the queue."""
        self.patch(status_listener.action_queue, "Download", FakeCommand)
        fake_command = FakeCommand()
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        self.listener.handle_SYS_QUEUE_REMOVED(fake_command)
        qc = self.status_frontend.aggregator.queued_commands
        self.assertNotIn(fake_command, qc)

    def test_upload_started(self):
        """An upload was added to the queue."""
        self.patch(status_listener.action_queue, "Upload", FakeCommand)
        fake_command = FakeCommand()
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        qc = self.status_frontend.aggregator.queued_commands
        self.assertIn(fake_command, qc)

    def test_upload_started_with_no_deflated_size(self):
        """An upload of unknown size was added to the queue."""
        self.patch(status_listener.action_queue, "Upload", FakeCommand)
        fake_command = FakeCommand()
        fake_command.deflated_size = None
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        qc = self.status_frontend.aggregator.queued_commands
        self.assertIn(fake_command, qc)

    def test_upload_finished(self):
        """An upload was removed from the queue."""
        self.patch(status_listener.action_queue, "Upload", FakeCommand)
        fake_command = FakeCommand()
        self.listener.handle_SYS_QUEUE_ADDED(fake_command)
        self.listener.handle_SYS_QUEUE_REMOVED(fake_command)
        qc = self.status_frontend.aggregator.queued_commands
        self.assertNotIn(fake_command, qc)

    def test_progress_made_on_upload(self):
        """Progress was made on an uploading file."""
        share_id = 'fake_share'
        node_id = 'fake_node'
        n_bytes_written = 100
        deflated_size = 10000
        self.listener.handle_AQ_UPLOAD_FILE_PROGRESS(
            share_id=share_id, node_id=node_id,
            n_bytes_written=n_bytes_written, deflated_size=deflated_size)
        pe = self.status_frontend.aggregator.progress_events
        self.assertEqual(
            [(share_id, node_id, n_bytes_written, deflated_size)], pe,
            "progress_made was not called (exactly once) on aggregator.")

    def test_progress_made_on_download(self):
        """Progress was made on an downloading file."""
        share_id = 'fake_share'
        node_id = 'fake_node'
        n_bytes_read = 200
        deflated_size = 20000
        self.listener.handle_AQ_DOWNLOAD_FILE_PROGRESS(
            share_id=share_id, node_id=node_id,
            n_bytes_read=n_bytes_read, deflated_size=deflated_size)
        pe = self.status_frontend.aggregator.progress_events
        self.assertEqual(
            [(share_id, node_id, n_bytes_read, deflated_size)], pe,
            "progress_made was not called (exactly once) on aggregator.")

    def test_queue_done(self):
        """The queue is empty."""
        fake_command = FakeCommand()
        qc = self.status_frontend.aggregator.queued_commands
        qc.add(fake_command)
        self.listener.handle_SYS_QUEUE_DONE()
        self.assertEqual(0, len(qc))

    def test_new_share_available(self):
        """A new share is available for subscription."""
        SHARE_ID = "fake share id"
        FAKE_SENDER = 'Mom'
        share = Share(volume_id=SHARE_ID, other_visible_name=FAKE_SENDER)
        self.fakevm.volumes[SHARE_ID] = share
        self.listener.handle_VM_SHARE_CREATED(SHARE_ID)
        self.assertEqual(
            2, len(self.status_frontend.notification.notifications_shown))

    def test_already_subscribed_new_udf_available(self):
        """A new udf that was already subscribed."""
        udf = UDF()
        udf.subscribed = True
        self.listener.handle_VM_UDF_CREATED(udf)
        self.assertEqual(
            1, len(self.status_frontend.notification.notifications_shown))

    def test_new_udf_available(self):
        """A new udf is available for subscription."""
        udf = UDF()
        self.listener.handle_VM_UDF_CREATED(udf)
        self.assertEqual(
            2, len(self.status_frontend.notification.notifications_shown))

    def test_two_new_udfs_available(self):
        """A new udf is available for subscription."""
        udf1 = UDF()
        self.listener.handle_VM_UDF_CREATED(udf1)
        udf2 = UDF()
        self.listener.handle_VM_UDF_CREATED(udf2)
        self.assertEqual(
            3, len(self.status_frontend.notification.notifications_shown))

    def test_server_connection_lost(self):
        """The client connected to the server."""
        self.status_frontend.aggregator.connected = True
        self.listener.handle_SYS_CONNECTION_LOST()
        self.assertEqual(
            1, len(self.status_frontend.notification.notifications_shown))
        self.assertFalse(self.status_frontend.aggregator.connected)

    def test_server_connection_made(self):
        """The client connected to the server."""
        self.status_frontend.aggregator.connected = False
        self.listener.handle_SYS_CONNECTION_MADE()
        self.assertEqual(
            1, len(self.status_frontend.notification.notifications_shown))
        self.assertTrue(self.status_frontend.aggregator.connected)

    def test_set_show_all_notifications(self):
        """Test the set_show_all_notifications method."""
        self.status_frontend.set_show_all_notifications(False)
        self.assertFalse(self.status_frontend.aggregator.
                         notification_switch.enabled)

    def test_udf_quota_exceeded(self):
        """Quota exceeded in udf."""
        mocker = Mocker()
        launcher = mocker.replace(
            "ubuntuone.platform.launcher.Launcher")
        launcher()
        mock_launcher = mocker.mock()
        mocker.result(mock_launcher)
        mock_launcher.set_urgent()
        mocker.replay()
        UDF_ID = 'fake udf id'
        udf = UDF(volume_id=UDF_ID)
        self.fakevm.volumes[UDF_ID] = udf
        self.listener.handle_SYS_QUOTA_EXCEEDED(
            volume_id=UDF_ID, free_bytes=0)
        self.assertEqual(
            1, len(self.status_frontend.notification.notifications_shown))
        mocker.restore()
        mocker.verify()

    def test_root_quota_exceeded(self):
        """Quota exceeded in root."""
        mocker = Mocker()
        launcher = mocker.replace(
            "ubuntuone.platform.launcher.Launcher")
        launcher()
        mock_launcher = mocker.mock()
        mocker.result(mock_launcher)
        mock_launcher.set_urgent()
        mocker.replay()
        ROOT_ID = 'fake root id'
        root = Root(volume_id=ROOT_ID)
        self.fakevm.volumes[ROOT_ID] = root
        self.fakevm.root = root
        self.listener.handle_SYS_QUOTA_EXCEEDED(
            volume_id=ROOT_ID, free_bytes=0)
        self.assertEqual(
            1, len(self.status_frontend.notification.notifications_shown))
        mocker.restore()
        mocker.verify()

    def test_share_quota_exceeded(self):
        """Quota exceeded in share."""
        mocker = Mocker()
        launcher = mocker.replace(
            "ubuntuone.platform.launcher.Launcher")
        launcher()
        mock_launcher = mocker.mock()
        mocker.result(mock_launcher)
        mock_launcher.set_urgent()
        launcher()
        mock_launcher = mocker.mock()
        mocker.result(mock_launcher)
        mock_launcher.set_urgent()
        mocker.replay()
        SHARE_ID = 'fake share id'
        BYTES = 0
        share = Share(volume_id=SHARE_ID)
        self.fakevm.volumes[SHARE_ID] = share
        self.listener.handle_SYS_QUOTA_EXCEEDED(SHARE_ID, BYTES)
        self.assertEqual(
            2, len(self.status_frontend.notification.notifications_shown))
        self.listener.handle_SYS_QUOTA_EXCEEDED(SHARE_ID, BYTES)
        self.listener.handle_SYS_QUOTA_EXCEEDED(SHARE_ID, BYTES)
        self.assertEqual(
            2, len(self.status_frontend.notification.notifications_shown))
        self.status_frontend.aggregator.clock.advance(aggregator.ONE_DAY + 1)
        self.listener.handle_SYS_QUOTA_EXCEEDED(SHARE_ID, BYTES)
        self.assertEqual(
            3, len(self.status_frontend.notification.notifications_shown))
        mocker.restore()
        mocker.verify()


class StatusEventTestCase(TestCase):
    """Test the status event class and children."""

    CLASS = aggregator.StatusEvent
    CLASS_KWARGS = {}
    status = None

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(StatusEventTestCase, self).setUp()
        if type(self) == StatusEventTestCase:
            self.assertRaises(AssertionError, self.CLASS, **self.CLASS_KWARGS)
        else:
            self.status = self.CLASS(**self.CLASS_KWARGS)

    def test_one_message_defined(self):
        """The singular message is defined as MESSAGE_ONE."""
        if self.status:
            self.assertNotEqual(None, self.CLASS.MESSAGE_ONE)

    def test_one_message_built_correctly(self):
        """The message returned by one() is returned ok."""
        if self.status:
            self.assertEqual(self.status.one(), self.CLASS.MESSAGE_ONE)


class FilePublishingStatusTestCase(StatusEventTestCase):
    """Test the file publishing status class."""

    CLASS = aggregator.FilePublishingStatus
    CLASS_KWARGS = {"new_public_url": "http://fake_public/url"}

    def test_one_message_built_correctly(self):
        """The message returned by one() should include the url."""
        expected = self.CLASS.MESSAGE_ONE % self.status.kwargs
        self.assertEqual(self.status.one(), expected)


class FileUnpublishingStatusTestCase(StatusEventTestCase):
    """Test the file unpublishing status class."""

    CLASS = aggregator.FileUnpublishingStatus
    CLASS_KWARGS = {"old_public_url": None}


class ShareAvailableEventTestCase(StatusEventTestCase):
    """Test the folder available status class with a Share."""

    FOLDER_NAME = "folder name"
    OTHER_USER_NAME = "person name"
    SAMPLE_SHARE = Share(accepted=False, name=FOLDER_NAME,
                         other_visible_name=OTHER_USER_NAME)
    CLASS = aggregator.ShareAvailableStatus
    CLASS_KWARGS = {"share": SAMPLE_SHARE}

    def test_one_message_built_correctly(self):
        """one() must return the folder name and user name."""
        format_args = {
            "folder_name": self.FOLDER_NAME,
            "other_user_name": self.OTHER_USER_NAME,
        }
        expected = self.CLASS.MESSAGE_ONE % format_args
        self.assertEqual(self.status.one(), expected)


class UDFAvailableEventTestCase(StatusEventTestCase):
    """Test the folder available status class with a UDF."""

    FOLDER_NAME = "folder name"
    SAMPLE_UDF = UDF(subscribed=False, suggested_path=FOLDER_NAME)
    CLASS = aggregator.UDFAvailableStatus
    CLASS_KWARGS = {'udf': SAMPLE_UDF}

    def test_one_message_built_correctly(self):
        """one() must return the folder name."""
        format_args = {"folder_name": self.FOLDER_NAME}
        expected = self.CLASS.MESSAGE_ONE % format_args
        self.assertEqual(self.status.one(), expected)


class ConnectionLostEventTestCase(StatusEventTestCase):
    """Test the event when the connection is lost."""

    CLASS = aggregator.ConnectionLostStatus

    def test_many_message_built_correctly(self):
        """The message returned by many() is returned ok."""
        if self.status:
            count = 99
            test_events = [FakeStatus(88)] * count + [self.CLASS()]
            expected = self.CLASS.MESSAGE_ONE
            self.assertEqual(self.status.many(test_events), expected)


class ConnectionMadeEventTestCase(ConnectionLostEventTestCase):
    """Test the event when the connection is made."""

    CLASS = aggregator.ConnectionMadeStatus


class FakeStatus(aggregator.StatusEvent):
    """A fake status to test weight comparisons."""

    def __init__(self, weight):
        """Initialize with the fake weight."""
        super(FakeStatus, self).__init__()
        self.WEIGHT = weight


class FakeFileDiscoveryBubble(object):
    """A fake FileDiscoveryBubble."""

    count = 0

    def __init__(self, status_aggregator, clock=None):
        """Initialize this instance."""
        self.status_aggregator = status_aggregator

    def new_file_found(self):
        """New files were found."""
        self.count += 1

    def cleanup(self):
        """Cleanup this instance."""

    def connection_made(self):
        """Connection made."""

    def connection_lost(self):
        """Connection lost."""


class FakeFinalBubble(object):
    """A fake FinalStatusBubble."""

    shown = False

    def __init__(self, status_aggregator):
        """Initialize this fake instance."""
        self.status_aggregator = status_aggregator

    def cleanup(self):
        """Cleanup this instance."""

    def show(self):
        """Show this bubble."""
        self.shown = True


class StatusAggregatorTestCase(TestCase):
    """Test the backend of the status aggregator."""

    @defer.inlineCallbacks
    def setUp(self):
        """Initialize this test instance."""
        yield super(StatusAggregatorTestCase, self).setUp()
        self.patch(aggregator, "FileDiscoveryBubble",
                   FakeFileDiscoveryBubble)
        self.patch(aggregator, "FinalStatusBubble",
                   FakeFinalBubble)
        self.patch(aggregator, "ToggleableNotification",
                   FakeNotificationSingleton())
        self.patch(aggregator, "Launcher", FakeLauncher)
        clock = PatchedClock()
        self.status_frontend = aggregator.StatusFrontend(clock=clock)
        self.aggregator = self.status_frontend.aggregator
        self.fake_bubble = self.aggregator.file_discovery_bubble

        self.handler = MementoHandler()
        self.handler.setLevel(logging.DEBUG)
        aggregator.logger.addHandler(self.handler)
        aggregator.logger.setLevel(logging.DEBUG)
        self.addCleanup(aggregator.logger.removeHandler, self.handler)
        self.addCleanup(self.aggregator.progress_bar.cleanup)

    def assertStatusReset(self):
        """Assert that the status is at zero."""
        self.assertEqual(0, self.aggregator.download_done)
        self.assertEqual(0, self.aggregator.upload_done)
        self.assertEqual(0, len(self.aggregator.files_uploading))
        self.assertEqual(0, len(self.aggregator.files_downloading))
        self.assertEqual({}, self.aggregator.progress)
        self.assertEqual({}, self.aggregator.to_do)
        self.assertIdentical(None, self.aggregator.queue_done_timer)

    def test_register_progress_listener(self):
        """Check that register listener handles properly additions."""

        def fake_callback():
            """Do nothing."""

        self.aggregator.register_progress_listener(fake_callback)
        self.assertEqual(len(self.aggregator.progress_listeners), 1)

    def test_register_progress_listener_fail(self):
        """Check that register listener fails with not Callable objects."""
        self.assertRaises(
            TypeError, self.aggregator.register_progress_listener, [])
        self.assertEqual(len(self.aggregator.progress_listeners), 0)

    def test_register_connection_listener(self):
        """Check that register listener handles properly additions."""

        def fake_callback():
            """Do nothing."""

        self.aggregator.register_connection_listener(fake_callback)
        self.assertEqual(len(self.aggregator.connection_listeners), 1)

    def test_register_connection_listener_fail(self):
        """Check that register listener fails with not Callable objects."""
        self.assertRaises(
            TypeError, self.aggregator.register_connection_listener, [])
        self.assertEqual(len(self.aggregator.connection_listeners), 0)

    def test_connection_notifications(self):
        """Check that the connection lister is notified."""
        data = {}

        def fake_callback(status):
            """Register status."""
            data['status'] = status

        self.aggregator.register_connection_listener(fake_callback)
        self.assertEqual(data, {})
        self.aggregator.connection_lost()
        self.assertFalse(data['status'])
        self.aggregator.connection_made()
        self.assertTrue(data['status'])

    def assertMiscCommandQueued(self, fc):
        """Assert that some command was queued."""
        self.assertEqual(len(self.aggregator.to_do), 1)
        message = "queueing command (total: 1): %s" % fc.__class__.__name__
        self.assertEqual(fc.deflated_size, sum(self.aggregator.to_do.values()))
        self.assertTrue(self.handler.check_debug(message))
        self.assertTrue(self.aggregator.progress_bar.visible)

    def assertMiscCommandUnqueued(self, fc):
        """Assert that some command was unqueued."""
        self.assertEqual(
            1, self.aggregator.download_done + self.aggregator.upload_done)
        message = "unqueueing command: %s" % fc.__class__.__name__
        self.assertTrue(self.handler.check_debug(message))

    def test_counters_start_at_zero(self):
        """Test that the counters start at zero."""
        self.assertStatusReset()

    def test_file_download_started(self):
        """Test that a file has started download."""
        fc = FakeCommand(path='testfile.txt')
        self.assertEqual('', self.aggregator.downloading_filename)
        self.status_frontend.download_started(fc)
        self.assertEqual(1, len(self.aggregator.files_downloading))
        self.assertEqual('testfile.txt', self.aggregator.downloading_filename)
        self.assertMiscCommandQueued(fc)
        self.assertEqual(1, self.fake_bubble.count)
        self.assertEqual(
            {(fc.share_id, fc.node_id): (fc.deflated_size)},
            self.aggregator.to_do)

    def test_file_download_finished(self):
        """Test that a file has finished downloading."""
        fc = FakeCommand()
        self.status_frontend.download_started(fc)
        self.status_frontend.download_finished(fc)
        self.assertEqual(self.aggregator.download_done, 1)
        self.assertMiscCommandUnqueued(fc)
        self.assertEqual(
            {(fc.share_id, fc.node_id): (fc.deflated_size)},
            self.aggregator.progress)
        self.assertEqual(len(self.aggregator.recent_transfers), 1)

    def test_file_upload_started(self):
        """Test that a file has started upload."""
        fc = FakeCommand(path='testfile.txt')
        self.assertEqual('', self.aggregator.uploading_filename)
        self.status_frontend.upload_started(fc)
        self.assertEqual(1, len(self.aggregator.files_uploading))
        self.assertEqual('testfile.txt', self.aggregator.uploading_filename)
        self.assertMiscCommandQueued(fc)
        self.assertEqual(1, self.fake_bubble.count)
        self.assertEqual(
            {(fc.share_id, fc.node_id): (fc.deflated_size)},
            self.aggregator.to_do)

    def test_file_upload_finished(self):
        """Test that a file has finished uploading."""
        fc = FakeCommand()
        self.status_frontend.upload_started(fc)
        self.status_frontend.upload_finished(fc)
        self.assertEqual(self.aggregator.upload_done, 1)
        self.assertMiscCommandUnqueued(fc)
        self.assertEqual(
            {(fc.share_id, fc.node_id): (fc.deflated_size)},
            self.aggregator.progress)
        self.assertEqual(len(self.aggregator.recent_transfers), 1)

    def test_max_recent_files(self):
        """Check that the queue doesn't exceed the 5 items."""
        for i in range(10):
            fc = FakeUploadCommand(str(i))
            self.status_frontend.upload_started(fc)
            self.status_frontend.upload_finished(fc)
        for i in range(10):
            fc = FakeDownloadCommand(str(i))
            self.status_frontend.download_started(fc)
            self.status_frontend.download_finished(fc)
        self.assertEqual(len(self.aggregator.recent_transfers), 5)

    def test_recent_transfers_is_unique(self):
        """Check that a given path is not repeated in recent transfers."""
        fc = FakeDownloadCommand('hi')
        self.status_frontend.download_started(fc)
        self.status_frontend.download_finished(fc)
        fc = FakeDownloadCommand('hi')
        self.status_frontend.download_started(fc)
        self.status_frontend.download_finished(fc)
        self.assertEqual(len(self.aggregator.recent_transfers), 1)

    def test_recent_transfers_reorders(self):
        """Check that if a transfer is repeated we put it back at the end."""
        fc = FakeDownloadCommand('hi')
        self.status_frontend.download_started(fc)
        self.status_frontend.download_finished(fc)
        fc = FakeDownloadCommand('howdy')
        self.status_frontend.download_started(fc)
        self.status_frontend.download_finished(fc)
        fc = FakeUploadCommand('hi')
        self.status_frontend.upload_started(fc)
        self.status_frontend.upload_finished(fc)

        self.assertEqual(len(self.aggregator.recent_transfers), 2)
        self.assertEqual(['howdy', 'hi'],
                         list(self.aggregator.recent_transfers))

    def test_progress_made(self):
        """Progress on up and downloads is tracked."""
        share_id = 'fake_share'
        node_id = 'fake_node'
        n_bytes = 200
        deflated_size = 100000
        self.aggregator.progress_made(
            share_id, node_id, n_bytes, deflated_size)
        self.assertEqual(
            {(share_id, node_id): (n_bytes)},
            self.aggregator.progress)

    def test_get_discovery_message(self):
        """Test the message that's shown on the discovery bubble."""
        uploading = 10
        downloading = 8
        filename = 'upfile0.ext'
        filename2 = 'downfile0.ext'
        self.aggregator.files_uploading.extend([
            FakeCommand(path='upfile%d.ext' % n) for n in range(uploading)])
        self.aggregator.uploading_filename = filename
        self.aggregator.files_downloading.extend([
            FakeCommand(path='downfile%d.ext' % n) for n in
            range(downloading)])
        self.aggregator.downloading_filename = filename2
        expected = (
            aggregator.files_being_uploaded(filename, uploading) + "\n" +
            aggregator.files_being_downloaded(filename2, downloading))
        result = self.aggregator.get_discovery_message()
        self.assertEqual(expected, result)

    def test_get_discovery_message_clears_filenames(self):
        """Test the message that's shown on the discovery bubble."""
        uploading = 10
        downloading = 8
        filename = 'upfile0.ext'
        filename2 = 'downfile0.ext'
        self.aggregator.files_uploading.extend([
            FakeCommand(path='upfile%d.ext' % n) for n in range(uploading)])
        self.aggregator.uploading_filename = filename
        self.aggregator.files_downloading.extend([
            FakeCommand(path='downfile%d.ext' % n) for n in
            range(downloading)])
        self.aggregator.downloading_filename = 'STALE FILENAME'
        self.aggregator.uploading_filename = 'STALE FILENAME'
        expected = (
            aggregator.files_being_uploaded(filename, uploading) + "\n" +
            aggregator.files_being_downloaded(filename2, downloading))
        result = self.aggregator.get_discovery_message()
        self.assertEqual(expected, result)

    def test_get_final_status_message(self):
        """The final status message."""
        done = (5, 10)
        self.aggregator.uploading_filename = FILENAME
        self.aggregator.downloading_filename = FILENAME2
        self.aggregator.upload_done, self.aggregator.download_done = done

        expected = (
            aggregator.FINAL_COMPLETED + "\n" +
            aggregator.files_were_uploaded(
                FILENAME, self.aggregator.upload_done) + "\n" +
            aggregator.files_were_downloaded(
                FILENAME2, self.aggregator.download_done))

        result = self.aggregator.get_final_status_message()
        self.assertEqual(expected, result)

    def test_get_final_status_message_no_uploads(self):
        """The final status message when there were no uploads."""
        done = (0, 12)
        self.aggregator.upload_done, self.aggregator.download_done = done
        self.aggregator.downloading_filename = FILENAME2

        expected = (
            aggregator.FINAL_COMPLETED + "\n" +
            aggregator.files_were_downloaded(
                FILENAME2, self.aggregator.download_done))

        result = self.aggregator.get_final_status_message()
        self.assertEqual(expected, result)

    def test_get_final_status_message_no_downloads(self):
        """The final status message when there were no downloads."""
        done = (8, 0)
        self.aggregator.upload_done, self.aggregator.download_done = done
        self.aggregator.uploading_filename = FILENAME

        expected = (
            aggregator.FINAL_COMPLETED + "\n" +
            aggregator.files_were_uploaded(
                FILENAME, self.aggregator.upload_done))

        result = self.aggregator.get_final_status_message()
        self.assertEqual(expected, result)

    def test_queue_done_shows_bubble_when_downloads_happened(self):
        """On queue done, show final bubble if downloads happened."""
        fc = FakeCommand()
        self.status_frontend.download_started(fc)
        self.status_frontend.download_finished(fc)
        old_final_bubble = self.aggregator.final_status_bubble
        self.aggregator.queue_done()
        self.aggregator.clock.advance(self.aggregator.finished_delay + 1)
        self.assertTrue(old_final_bubble.shown)

    def test_queue_done_shows_bubble_when_uploads_happened(self):
        """On queue done, show final bubble if uploads happened."""
        fc = FakeCommand()
        self.status_frontend.upload_started(fc)
        self.status_frontend.upload_finished(fc)
        old_final_bubble = self.aggregator.final_status_bubble
        self.aggregator.queue_done()
        self.aggregator.clock.advance(self.aggregator.finished_delay + 1)
        self.assertTrue(old_final_bubble.shown)

    def test_queue_done_shows_bubble_only_after_delay(self):
        """On queue_done, show final bubble only after a delay."""
        fc = FakeCommand()
        self.status_frontend.upload_started(fc)
        self.status_frontend.upload_finished(fc)
        old_final_bubble = self.aggregator.final_status_bubble
        self.aggregator.queue_done()
        self.assertFalse(old_final_bubble.shown)
        self.aggregator.clock.advance(self.aggregator.finished_delay - 1)
        self.assertFalse(old_final_bubble.shown)
        self.aggregator.queue_done()
        self.assertFalse(old_final_bubble.shown)
        self.aggregator.clock.advance(2)
        self.assertFalse(old_final_bubble.shown)
        self.aggregator.clock.advance(self.aggregator.finished_delay + 1)
        self.assertTrue(old_final_bubble.shown)

    def test_queue_done_does_not_show_bubble_when_no_transfers_happened(self):
        """On queue done, don't show final bubble if no transfers happened."""
        fc = FakeCommand()
        self.status_frontend.upload_started(fc)
        old_final_bubble = self.aggregator.final_status_bubble
        self.aggregator.queue_done()
        self.assertFalse(old_final_bubble.shown)

    def test_queue_done_resets_status_and_hides_progressbar(self):
        """On queue done, reset counters and hide progressbar."""
        fc = FakeCommand()
        self.status_frontend.upload_started(fc)
        self.aggregator.queue_done()
        self.aggregator.clock.advance(self.aggregator.finished_delay + 1)
        self.assertStatusReset()
        self.assertEqual(0.0, self.aggregator.progress_bar.progress)
        self.assertFalse(self.aggregator.progress_bar.visible)

    def test_download_started_cancels_timer(self):
        """Starting a download cancels the queue_done timer."""
        fc = FakeCommand()
        self.status_frontend.download_started(fc)
        self.aggregator.clock.advance(self.aggregator.finished_delay)
        self.status_frontend.download_finished(fc)
        self.aggregator.queue_done()
        self.aggregator.clock.advance(self.aggregator.finished_delay / 2)
        fc2 = FakeCommand()
        self.status_frontend.download_started(fc2)
        self.assertIdentical(self.aggregator.queue_done_timer, None)
        self.aggregator.clock.advance(self.aggregator.finished_delay)
        self.status_frontend.download_finished(fc2)

    def test_upload_started_cancels_timer(self):
        """Starting an upload cancels the queue_done timer."""
        fc = FakeCommand()
        self.status_frontend.upload_started(fc)
        self.aggregator.clock.advance(self.aggregator.finished_delay)
        self.status_frontend.upload_finished(fc)
        self.aggregator.queue_done()
        self.aggregator.clock.advance(self.aggregator.finished_delay / 2)
        fc2 = FakeCommand()
        self.status_frontend.upload_started(fc2)
        self.assertIdentical(self.aggregator.queue_done_timer, None)
        self.aggregator.clock.advance(self.aggregator.finished_delay)
        self.status_frontend.upload_finished(fc2)


class StatusGrouperTestCase(TestCase):
    """Tests for the group_statuses function."""

    def test_group_status(self):
        """The status grouper sorts and groups by weight."""
        status99 = FakeStatus(99)
        statuses = [
            status99,
            status99,
            FakeStatus(12),
            FakeStatus(1)]

        result = [list(k) for _, k in aggregator.group_statuses(statuses)]
        expected = [
            [statuses[3]],
            [statuses[2]],
            [status99, status99]]

        self.assertEqual(result, expected)


class HundredFeetTestCase(TestCase):
    """Try to make all parts work together."""

    def test_all_together_now(self):
        """Make all parts work together."""
        self.patch(aggregator, "ToggleableNotification",
                   FakeNotificationSingleton())
        self.patch(aggregator, "Launcher", FakeLauncher)
        self.patch(aggregator.session, "Inhibitor", FakeInhibitor)
        clock = PatchedClock()
        upload = FakeCommand(path='upload.foo')
        sf = aggregator.StatusFrontend(clock=clock)
        sf.server_connection_made()
        sf.set_show_all_notifications(True)

        # the progress bar is not visible yet
        self.assertFalse(sf.aggregator.progress_bar.visible)
        sf.upload_started(upload)
        # the progress bar is now shown
        self.assertTrue(sf.aggregator.progress_bar.visible)
        notifications_shown = (sf.aggregator.file_discovery_bubble.
                               notification.notifications_shown)
        # no notifications shown yet
        self.assertEqual(0, len(notifications_shown))
        clock.advance(aggregator.FileDiscoveryGatheringState.initial_delay)
        # files found notification
        self.assertEqual(1, len(notifications_shown))
        download = FakeCommand('download.bar')
        sf.download_started(download)
        self.assertEqual(1, len(notifications_shown))
        # the progress still is zero
        self.assertEqual(0.0, sf.aggregator.progress_bar.progress)
        clock.advance(aggregator.FileDiscoveryUpdateState.updates_delay)
        # files count update
        self.assertEqual(2, len(notifications_shown))
        clock.advance(aggregator.FileDiscoveryUpdateState.updates_timeout -
                      aggregator.FileDiscoveryUpdateState.updates_delay)
        sf.upload_finished(upload)
        sf.download_finished(download)
        # the progress still is now 100%
        self.assertEqual(1.0, sf.aggregator.progress_bar.progress)
        sf.queue_done()
        clock.advance(sf.aggregator.finished_delay + 1)
        self.assertEqual(3, len(notifications_shown))

    def test_all_together_now_off(self):
        """Make all parts work together, but with notifications off."""
        self.patch(aggregator, "ToggleableNotification",
                   FakeNotificationSingleton())
        self.patch(aggregator, "Launcher", FakeLauncher)
        self.patch(aggregator.session, "Inhibitor", FakeInhibitor)
        clock = PatchedClock()
        upload = FakeCommand('upload.foo')
        sf = aggregator.StatusFrontend(clock=clock)
        sf.set_show_all_notifications(False)

        # the progress bar is not visible yet
        self.assertFalse(sf.aggregator.progress_bar.visible)
        sf.upload_started(upload)
        # the progress bar is now shown
        self.assertTrue(sf.aggregator.progress_bar.visible)
        notifications_shown = (sf.aggregator.file_discovery_bubble.
                               notification.notifications_shown)
        # no notifications shown, never
        self.assertEqual(0, len(notifications_shown))
        clock.advance(aggregator.FileDiscoveryGatheringState.initial_delay)
        self.assertEqual(0, len(notifications_shown))
        download = FakeCommand('download.bar')
        sf.download_started(download)
        self.assertEqual(0, len(notifications_shown))
        # the progress still is zero
        self.assertEqual(0.0, sf.aggregator.progress_bar.progress)
        clock.advance(aggregator.FileDiscoveryUpdateState.updates_delay)
        self.assertEqual(0, len(notifications_shown))
        clock.advance(aggregator.FileDiscoveryUpdateState.updates_timeout -
                      aggregator.FileDiscoveryUpdateState.updates_delay)
        sf.upload_finished(upload)
        sf.download_finished(download)
        # the progress still is now 100%
        self.assertEqual(1.0, sf.aggregator.progress_bar.progress)
        self.assertEqual(0, len(notifications_shown))
        sf.queue_done()
        self.assertEqual(0, len(notifications_shown))

HundredFeetTestCase.skip = "libindicate-ERROR causes core dump: #922179"
