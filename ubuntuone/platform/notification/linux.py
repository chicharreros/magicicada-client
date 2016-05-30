# Copyright 2011-2013 Canonical Ltd.
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
"""Module that implements notification of the end user."""

# TODO: We may want to enable different notifiers. When none of them
# are available, we should fall back to silently discarding
# notifications.
USE_NOTIFY = False

try:
    from gi.repository import Notify
    USE_NOTIFY = True
except ImportError:
    pass

from ubuntuone.clientdefs import NAME
from ubuntuone.status.notification import AbstractNotification

ICON_NAME = NAME.lower()


class Notification(AbstractNotification):
    """Notification of the end user."""

    def __init__(self, application_name=NAME):
        self.application_name = application_name
        self.notification = None

    def send_notification(self, title, message, icon=ICON_NAME, append=False):
        """Send a notification using the underlying library."""
        if not USE_NOTIFY:
            return

        if self.notification is None:
            Notify.init(self.application_name)
            self.notification = Notify.Notification.new(title, message,
                                                        icon)
        else:
            self.notification.update(title, message, icon)

        if append:
            self.notification.set_hint_string('x-canonical-append', '')

        self.notification.set_hint_int32('transient', int(True))
        self.notification.show()
