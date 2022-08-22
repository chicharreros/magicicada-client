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

"""Test the skip decorators."""

import os
import sys

from twisted.trial.runner import LoggedSuite
from twisted.trial.reporter import TestResult

from devtools import testcases
from devtools.testcases import BaseTestCase

OTHER_PLATFORM = {"darwin": "win32", "win32": "linux2", "linux2": "win32"}


class TestSkipBasicDecorators(BaseTestCase):
    """Test skipping decorators."""

    def test_skip_decorators(self):
        """Test the decorators that skip tests."""
        self.patch(os, "getenv", lambda *args: True)

        operations_table = (
            (
                testcases.skipIf,
                (False, "False condition"),
                (True, "True condition"),
            ),
            (
                testcases.skipIfOS,
                (OTHER_PLATFORM[sys.platform], "skipIf other platform"),
                (sys.platform, "skipIf this platform"),
            ),
            (
                testcases.skipIfNotOS,
                (sys.platform, "skipIfNot this platform"),
                (OTHER_PLATFORM[sys.platform], "skipIfNot other platform"),
            ),
            (
                testcases.skipIfJenkins,
                (OTHER_PLATFORM[sys.platform], "skipIfJenkins other platform"),
                (sys.platform, "skipIfJenkins this platform"),
            ),
        )
        for deco, dont_skip, do_skip in operations_table:

            class Foo(BaseTestCase):
                """Dummy test case used for the decorators testing."""

                @deco(*do_skip)
                def test_skip(self):
                    """Test to skip."""
                    pass

                @deco(*dont_skip)
                def test_dont_skip(self):
                    """Test not to skip."""
                    pass

            test_do_skip = Foo("test_skip")
            test_dont_skip = Foo("test_dont_skip")
            suite = LoggedSuite([test_do_skip, test_dont_skip])
            result = TestResult()
            suite.run(result)
            self.assertEqual(len(result.skips), 1)
            self.assertEqual(result.successes, 1)
            self.assertEqual(result.skips, [(test_do_skip, do_skip[1])])

    def test_skip_class(self):
        """Test skipping a full test class."""

        class Foo(BaseTestCase):
            """Test class to be skipped."""

            def test_1(self):
                """First test to skip."""
                record.append(1)

            def test_2(self):
                """Second test to skip."""
                record.append(1)

        # Decorate the class.
        Foo = testcases.skipTest("testing")(Foo)
        record = []
        result = TestResult()
        test = Foo("test_1")
        suite = LoggedSuite([test])
        suite.run(result)
        self.assertEqual(result.skips, [(test, "testing")])
        self.assertEqual(record, [])
