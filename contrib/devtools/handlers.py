# -*- coding: utf-8 -*-

# Author: Guillermo Gonzalez <guillermo.gonzalez@canonical.com>
# Author: Facundo Batista <facundo@canonical.com>
#
# Copyright 2009-2012 Canonical Ltd.
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
"""Set of helpers handlers."""

from __future__ import print_function

import logging


class MementoHandler(logging.Handler):
    """ A handler class which store logging records in a list """

    def __init__(self, *args, **kwargs):
        """ Create the instance, and add a records attribute. """
        logging.Handler.__init__(self, *args, **kwargs)
        self.records = []
        self.debug = False

    def emit(self, record):
        """ Just add the record to self.records. """
        self.format(record)
        self.records.append(record)

    def dump_contents(self):
        """Dumps the contents of the MementoHandler."""
        for rec in self.records:
            print("\t", rec.exc_info)
            print("\t", logging.getLevelName(rec.levelno))
            print("\t\t", rec.message)
            print("\t\t", rec.exc_text)

    def check(self, level, *msgs):
        """Verifies that the msgs are logged in the specified level"""
        for rec in self.records:
            if rec.levelno == level and all(m in rec.message for m in msgs):
                return rec
        if self.debug:
            print("Expecting:")
            for msg in msgs:
                print("\t", msg)
            print("MementoHandler contents:")
            self.dump_contents()
        return False

    def check_debug(self, *msgs):
        """Shortcut for checking in DEBUG."""
        return self.check(logging.DEBUG, *msgs)

    def check_info(self, *msgs):
        """Shortcut for checking in INFO."""
        return self.check(logging.INFO, *msgs)

    def check_warning(self, *msgs):
        """Shortcut for checking in WARNING."""
        return self.check(logging.WARNING, *msgs)

    def check_error(self, *msgs):
        """Shortcut for checking in ERROR."""
        return self.check(logging.ERROR, *msgs)

    def check_exception(self, exception_info, *msgs):
        """Shortcut for checking exceptions."""
        for rec in self.records:
            if rec.levelno == logging.ERROR and \
                    all(m in rec.exc_text + rec.message for m in msgs) and \
                    exception_info in rec.exc_info:
                return True
        return False
