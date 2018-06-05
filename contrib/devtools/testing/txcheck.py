# -*- coding: utf-8 -*-

# Author: Tim Cole <tim.cole@canonical.com>
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
"""Utilities for performing correctness checks."""

import sys
import ast
from inspect import getsource
from textwrap import dedent
from itertools import takewhile
from unittest import TestCase, TestSuite, TestResult

from twisted.trial.unittest import TestCase as TwistedTestCase


def type_to_name(type_obj):
    """Return a name for a type."""
    package_name = getattr(type_obj, '__module__', None)
    if package_name:
        return "%s.%s" % (package_name, type_obj.__name__)
    else:
        return type_obj.__name__


class Problem(AssertionError):
    """An object representing a problem in a method."""

    def __init__(self, method, test_class, ancestor_class):
        """Initialize an instance."""
        super(Problem, self).__init__()
        self.method = method
        self.test_class = test_class
        self.ancestor_class = ancestor_class

    def __eq__(self, other):
        """Test equality."""
        return type(self) == type(other) and self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Test inequality."""
        return not (self == other)

    def __hash__(self):
        """Return hash."""
        member_hash = 0
        for (key, value) in self.__dict__.items():
            member_hash ^= hash(key) ^ hash(value)
        return hash(type(self)) ^ member_hash

    def __str__(self):
        """Return a friendlier representation."""
        if self.ancestor_class != self.test_class:
            method_string = ("%s in ancestor method %s.%s" %
                             (type_to_name(self.test_class),
                              type_to_name(self.ancestor_class),
                              self.method))
        else:
            method_string = ("%s.%s" %
                             (type_to_name(self.test_class), self.method))
        return ("%s for %s" % (type(self).__name__, method_string))

    def __repr__(self):
        """Return representation string."""
        return "<%s %r>" % (type(self), self.__dict__)


class MethodShadowed(Problem):
    """Problem when trial's run method is shadowed."""


class SuperResultDiscarded(Problem):
    """Problem when callback chains are broken."""


class SuperNotCalled(Problem):
    """Problem when super isn't called."""


class MissingInlineCallbacks(Problem):
    """Problem when the inlineCallbacks decorator is missing."""


class MissingReturnValue(Problem):
    """Problem when there's no return value."""


def match_type(expected_type):
    """Return predicate matching nodes of given type."""
    return lambda node: isinstance(node, expected_type)


def match_equal(expected_value):
    """Return predicate matching nodes equaling the given value."""
    return lambda node: expected_value == node


def match_in(expected_values):
    """Return predicate matching node if in collection of expected values."""
    return lambda node: node in expected_values


def match_not_none():
    """Returns a predicate matching nodes which are not None."""
    return lambda node: node is not None


def match_any(*subtests):
    """Return short-circuiting predicate matching any given subpredicate."""
    if len(subtests) == 1:
        return subtests[0]
    else:

        def test(node):
            """Try each subtest until we find one that passes."""
            for subtest in subtests:
                if subtest(node):
                    return True
            return False

        return test


def match_all(*subtests):
    """Return short-circuiting predicate matching all given subpredicates."""
    if len(subtests) == 1:
        return subtests[0]
    else:

        def test(node):
            """Try each subtest until we find one that fails."""
            for subtest in subtests:
                if not subtest(node):
                    return False
            return True

        return test


def match_attr(attr_name, *tests):
    """Return predicate matching subpredicates against an attribute value."""
    return lambda node: match_all(*tests)(getattr(node, attr_name))


def match_path(initial_test, *components):
    """Return predicate which recurses into the tree via given attributes."""
    components = list(components)
    components.reverse()

    def test(node):
        return True

    for component in components:
        attr_name = component[0]
        subtests = component[1:]
        test = match_attr(attr_name, match_all(match_all(*subtests), test))
    return match_all(initial_test, test)


def match_child(*tests):
    """Return predicate which tests any child."""
    subtest = match_all(*tests)

    def test(node):
        """Try each child until we find one that matches."""
        for child in ast.iter_child_nodes(node):
            if subtest(child):
                return True
        return False

    return test


def match_descendant(subtest, prune):
    """Return predicate which tests a node and any descendants."""

    def test(node):
        """Recursively (breadth-first) search for a matching node."""
        for child in ast.iter_child_nodes(node):
            if prune(child):
                continue
            if subtest(child) or test(child):
                return True
        return False

    return test


def matches(node, *tests):
    """Convenience function to try predicates on a node."""
    return match_all(*tests)(node)


def any_matches(nodes, *tests):
    """Convenience function to try predicates on any of a sequence of nodes."""
    test = match_all(*tests)
    for node in nodes:
        if test(node):
            return True
    return False


def iter_matching_child_nodes(node, *tests):
    """Yields every matching child node."""
    test = match_all(*tests)
    for child in ast.iter_child_nodes(node):
        if test(child):
            yield child


SETUP_FUNCTION_NAMES = ('setUp', 'tearDown')
SETUP_FUNCTION = match_path(match_type(ast.FunctionDef),
                            ('name', match_in(SETUP_FUNCTION_NAMES)))

SUPER = match_path(match_type(ast.Call),
                   ('func', match_type(ast.Attribute)),
                   ('value', match_type(ast.Call)),
                   ('func', match_type(ast.Name)),
                   ('id', match_equal("super")))

BARE_SUPER = match_path(match_type(ast.Expr),
                        ('value', SUPER))

YIELD = match_type(ast.Yield)

INLINE_CALLBACKS_DECORATOR = \
    match_any(match_path(match_type(ast.Attribute),
                         ('attr', match_equal('inlineCallbacks'))),
              match_path(match_type(ast.Name),
                         ('id', match_equal('inlineCallbacks'))))

RETURN_VALUE = \
    match_path(match_type(ast.Return),
               ('value', match_not_none()))

DEFS = match_any(match_type(ast.ClassDef),
                 match_type(ast.FunctionDef))


def find_problems(class_to_check):
    """Check twisted test setup in a given test class."""
    mro = class_to_check.__mro__
    if TwistedTestCase not in mro:
        return set()

    problems = set()

    ancestry = takewhile(lambda c: c != TwistedTestCase, mro)
    for ancestor_class in ancestry:
        if 'run' in ancestor_class.__dict__:
            problem = MethodShadowed(method='run',
                                     test_class=class_to_check,
                                     ancestor_class=ancestor_class)
            problems.add(problem)

        source = dedent(getsource(ancestor_class))
        tree = ast.parse(source)
        # the top level of the tree is a Module
        class_node = tree.body[0]

        # Check setUp/tearDown
        for def_node in iter_matching_child_nodes(class_node, SETUP_FUNCTION):
            if matches(def_node, match_child(BARE_SUPER)):
                # Superclass method called, but its result wasn't used
                problem = SuperResultDiscarded(method=def_node.name,
                                               test_class=class_to_check,
                                               ancestor_class=ancestor_class)
                problems.add(problem)
            if not matches(def_node, match_descendant(SUPER, DEFS)):
                # The call to the overridden superclass method is missing
                problem = SuperNotCalled(method=def_node.name,
                                         test_class=class_to_check,
                                         ancestor_class=ancestor_class)
                problems.add(problem)

            decorators = def_node.decorator_list

            if matches(def_node, match_descendant(YIELD, DEFS)):
                # Yield was used, making this a generator
                if not any_matches(decorators, INLINE_CALLBACKS_DECORATOR):
                    # ...but the inlineCallbacks decorator is missing
                    problem = MissingInlineCallbacks(
                        method=def_node.name,
                        test_class=class_to_check,
                        ancestor_class=ancestor_class)
                    problems.add(problem)
            else:
                if not matches(def_node, match_descendant(RETURN_VALUE, DEFS)):
                    # The function fails to return a deferred
                    problem = MissingReturnValue(
                        method=def_node.name,
                        test_class=class_to_check,
                        ancestor_class=ancestor_class)
                    problems.add(problem)

    return problems


def get_test_classes(suite):
    """Return all the unique test classes involved in a suite."""
    classes = set()

    def find_classes(suite_or_test):
        """Recursively find all the test classes."""
        if isinstance(suite_or_test, TestSuite):
            for subtest in suite_or_test:
                find_classes(subtest)
        else:
            classes.add(type(suite_or_test))

    find_classes(suite)

    return classes


def make_check_testcase(tests):
    """Make TestCase which checks the given twisted tests."""

    class TXCheckTest(TestCase):
        """Test case which checks the test classes for problems."""

        def runTest(self):  # pylint: disable=C0103
            """Do nothing."""

        def run(self, result=None):
            """Check all the test classes for problems."""
            if result is None:
                result = TestResult()

            test_classes = set()

            for test_object in tests:
                test_classes |= get_test_classes(test_object)

            for test_class in test_classes:
                problems = find_problems(test_class)
                for problem in problems:
                    try:
                        raise problem
                    except Problem:
                        result.addFailure(self, sys.exc_info())

    return TXCheckTest()


class TXCheckSuite(TestSuite):
    """Test suite which checks twisted tests."""

    def __init__(self, tests=()):
        """Initialize with the given tests, and add a special test."""

        tests = list(tests)
        tests.insert(0, make_check_testcase(self))

        super(TXCheckSuite, self).__init__(tests)
