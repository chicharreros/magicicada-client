# Copyright 2010-2013 Canonical Ltd.
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
"""
Test the notification on linux. These tests are kind of stupid, but at
least they ensure 100% coverage and hence no silly/syntax errors.
"""

from mocker import Mocker
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from ubuntuone.platform.notification import Notification, ICON_NAME

FAKE_APP_NAME = "Teh wonderful app."
FAKE_TITLE = "Sous titre"
FAKE_MESSAGE = "Oi! You there!"
FAKE_APPENDAGE = "Appendix I."
FAKE_ICON = "fakicon"
FAKE_NEW_TITLE = "Nouveau titre"
FAKE_NEW_MESSAGE = "HELLOOOOOO"
FAKE_NEW_ICON = "novicon"


def callback(indicator, message_time=None):
    """Dummy callback."""
    pass


class NotificationTestCase(TestCase):
    """Test the Messaging API."""

    @defer.inlineCallbacks
    def setUp(self):
        yield super(NotificationTestCase, self).setUp()
        self.mocker = Mocker()

    @defer.inlineCallbacks
    def tearDown(self):
        yield super(NotificationTestCase, self).tearDown()
        self.mocker.restore()
        self.mocker.verify()

    def _set_up_mock_notify(self, title, message, icon):
        """Set up the mock_notify expectations."""
        mock_notify = self.mocker.replace('gi.repository.Notify')
        mock_notify.init(FAKE_APP_NAME)
        mock_notify.Notification.new(title, message, icon)

    def test_send_notification(self):
        """On notification, pynotify receives the proper calls."""
        self._set_up_mock_notify(FAKE_TITLE, FAKE_MESSAGE, ICON_NAME)
        mock_notification = self.mocker.mock()
        self.mocker.result(mock_notification)
        mock_notification.set_hint_int32('transient', int(True))
        mock_notification.show()
        self.mocker.replay()
        Notification(FAKE_APP_NAME).send_notification(FAKE_TITLE, FAKE_MESSAGE)

    def test_send_two_notifications(self):
        """On notification, pynotify receives the proper calls."""
        self._set_up_mock_notify(FAKE_TITLE, FAKE_MESSAGE, ICON_NAME)
        mock_notification = self.mocker.mock()
        self.mocker.result(mock_notification)
        mock_notification.set_hint_int32('transient', int(True))
        mock_notification.show()
        mock_notification.update(
            FAKE_TITLE + '2', FAKE_MESSAGE + '2', ICON_NAME)
        mock_notification.set_hint_int32('transient', int(True))
        mock_notification.show()
        self.mocker.replay()
        notifier = Notification(FAKE_APP_NAME)
        notifier.send_notification(FAKE_TITLE, FAKE_MESSAGE)
        notifier.send_notification(FAKE_TITLE + '2', FAKE_MESSAGE + '2')

    def test_send_notification_with_icon(self):
        """On notification with icon, pynotify receives the proper calls."""
        self._set_up_mock_notify(FAKE_TITLE, FAKE_MESSAGE, FAKE_ICON)
        mock_notification = self.mocker.mock()
        self.mocker.result(mock_notification)
        mock_notification.set_hint_int32('transient', int(True))
        mock_notification.show()
        self.mocker.replay()
        Notification(FAKE_APP_NAME).send_notification(
            FAKE_TITLE, FAKE_MESSAGE, FAKE_ICON)

    def test_append_notification(self):
        """On notification append, pynotify receives the proper calls."""
        self._set_up_mock_notify(FAKE_TITLE, FAKE_MESSAGE, ICON_NAME)
        mock_notification = self.mocker.mock()
        self.mocker.result(mock_notification)
        mock_notification.set_hint_string('x-canonical-append', '')
        mock_notification.set_hint_int32('transient', int(True))
        mock_notification.show()
        mock_notification.update(FAKE_TITLE, FAKE_APPENDAGE, ICON_NAME)
        mock_notification.set_hint_string('x-canonical-append', '')
        mock_notification.set_hint_int32('transient', int(True))
        mock_notification.show()
        self.mocker.replay()
        notifier = Notification(FAKE_APP_NAME)
        notifier.send_notification(FAKE_TITLE, FAKE_MESSAGE, append=True)
        notifier.send_notification(FAKE_TITLE, FAKE_APPENDAGE, append=True)
