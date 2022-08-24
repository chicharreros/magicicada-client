# Copyright 2011-2012 Canonical Ltd.
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

"""Tests for check functions."""

from unittest import TestCase, TestResult
from twisted.trial.unittest import TestCase as TwistedTestCase
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks

from devtools.testing.txcheck import (
    find_problems,
    MethodShadowed,
    MissingReturnValue,
    SuperNotCalled,
    SuperResultDiscarded,
    MissingInlineCallbacks,
    TXCheckSuite,
)


class TestCheckTwistedTestClass(TestCase):
    """Test checks for twisted test classes."""

    def test_not_twisted(self):
        """Check that we handle non-twisted test cases."""

        class Simple(TestCase):
            """Boring non-twisted test case."""

        problems = find_problems(Simple)
        self.assertEqual(problems, set())

    def test_no_problems(self):
        """Check that we don't spuriously report problems."""

        class SimpleTwisted(TwistedTestCase):
            """Boring twisted test case."""

        problems = find_problems(SimpleTwisted)
        self.assertEqual(problems, set())

    def test_ok_mixin_order(self):
        """Test that acceptable mixin order gets a pass."""

        class OtherTestCase(TestCase):
            """A test case class that overrides run."""

            def run(self):
                """Do nothing."""

        class OkMixin(TwistedTestCase, OtherTestCase):
            """Mixin where trial's run method comes first."""

        problems = find_problems(OkMixin)
        self.assertEqual(problems, set())

    def test_bad_mixin_order(self):
        """Check that we catch bad mixin order."""

        class OtherTestCase(TestCase):
            """A test case class that overrides run."""

            def run(self):
                """Do nothing."""

        class BadMixin(OtherTestCase, TwistedTestCase):
            """Mixin where trial's run method gets shadowed."""

        problems = find_problems(BadMixin)
        expected_problem = MethodShadowed(
            method='run', test_class=BadMixin, ancestor_class=OtherTestCase
        )
        self.assertEqual(problems, set([expected_problem]))

    def test_missing_return(self):
        """Test that we detect missing return statements."""

        class MissingReturnCase(TwistedTestCase):
            """A test class that fails to return deferreds."""

            def setUp(self):
                """Call super but discard its result."""
                d = super(MissingReturnCase, self).setUp()
                d.addCallback(lambda r: r)

            def tearDown(self):
                """Call super but discard its result."""
                d = super(MissingReturnCase, self).tearDown()
                d.addCallback(lambda r: r)

        problems = find_problems(MissingReturnCase)
        self.assertEqual(
            problems,
            set(
                [
                    MissingReturnValue(
                        method=m,
                        test_class=MissingReturnCase,
                        ancestor_class=MissingReturnCase,
                    )
                    for m in ('setUp', 'tearDown')
                ]
            ),
        )

    def test_super_not_called(self):
        """Test that we detect missing super()."""

        class NoSuperCase(TwistedTestCase):
            """A test class that doesn't call super()."""

            def setUp(self):
                """Don't call super()."""
                return 3

            def tearDown(self):
                """Don't call super()."""
                return 3

        problems = find_problems(NoSuperCase)
        self.assertEqual(
            problems,
            set(
                [
                    SuperNotCalled(
                        method=m,
                        test_class=NoSuperCase,
                        ancestor_class=NoSuperCase,
                    )
                    for m in ('setUp', 'tearDown')
                ]
            ),
        )

    def test_bare_super(self):
        """Test that we detect bare super()."""

        class BareSuperCase(TwistedTestCase):
            """A test class that discards the superclass return value."""

            def setUp(self):
                """Don't do anything with the superclass setUp result."""
                super(BareSuperCase, self).setUp()
                return 3

            def tearDown(self):
                """Don't do anything with the superclass tearDown result."""
                super(BareSuperCase, self).tearDown()
                return 3

        problems = find_problems(BareSuperCase)
        self.assertEqual(
            problems,
            set(
                [
                    SuperResultDiscarded(
                        method=m,
                        test_class=BareSuperCase,
                        ancestor_class=BareSuperCase,
                    )
                    for m in ('setUp', 'tearDown')
                ]
            ),
        )

    def test_inline_callbacks_missing(self):
        """Test that we detect missing inlineCallbacks."""

        class NoInlineCallbacksCase(TwistedTestCase):
            """A test class that is missing inlineCallbacks."""

            def setUp(self):
                """Yield result of superclass method."""
                yield super(NoInlineCallbacksCase, self).setUp()

            def tearDown(self):
                """Yield result of superclass method."""
                yield super(NoInlineCallbacksCase, self).tearDown()

        problems = find_problems(NoInlineCallbacksCase)
        self.assertEqual(
            problems,
            set(
                [
                    MissingInlineCallbacks(
                        method=m,
                        test_class=NoInlineCallbacksCase,
                        ancestor_class=NoInlineCallbacksCase,
                    )
                    for m in ('setUp', 'tearDown')
                ]
            ),
        )

    def test_inline_callbacks(self):
        """Test that has inline callbacks, as it should."""

        class InlineCallbacksCase(TwistedTestCase):
            """A test class that does what it should."""

            @defer.inlineCallbacks
            def setUp(self):
                """Yield result of superclass method."""
                yield super(InlineCallbacksCase, self).setUp()

            @inlineCallbacks
            def tearDown(self):
                """Yield result of superclass method."""
                yield super(InlineCallbacksCase, self).tearDown()

        problems = find_problems(InlineCallbacksCase)
        self.assertEqual(problems, set())


class TestTwistedCheckSuite(TestCase):
    """Check the behavior of TXCheckSuite."""

    def test_suite_runs_tests(self):
        """Verify that the test suite runs tests."""

        has_run = []

        class ATestCase(TwistedTestCase):
            """Simple test case that just records being run."""

            def runTest(self):
                """Record that the test has been run."""
                has_run.append(None)

        suite = TXCheckSuite()
        suite.addTest(ATestCase())
        result = TestResult()
        suite.run(result)
        self.assertEqual(len(has_run), 1)

    def test_suite_catches_problems(self):
        """Verify that the test suite class catches problems in tests."""

        class BrokenTestCase(TwistedTestCase):
            """Test case with a broken setUp."""

            def setUp(self):
                """Call superclass method but discard its result."""
                super(BrokenTestCase, self).setUp()
                return 3

            def runTest(self):
                """Do nothing."""

        suite = TXCheckSuite()
        test_case = BrokenTestCase()
        suite.addTest(test_case)
        result = TestResult()
        suite.run(result)

        self.assertEqual(len(result.failures), 1)
        failure = result.failures[0][1]
        package_name = type(self).__module__
        class_name = BrokenTestCase.__name__
        full_method_name = "%s.%s.setUp" % (package_name, class_name)
        self.assertNotEqual(failure.find("SuperResultDiscarded"), -1)
        self.assertNotEqual(failure.find(full_method_name), -1)
