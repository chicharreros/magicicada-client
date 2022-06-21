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

"""Base tests cases and test utilities."""

import contextlib
import os
import shutil
import sys

from functools import wraps

from twisted.trial.unittest import TestCase, SkipTest


@contextlib.contextmanager
def environ(env_var, new_value):
    """context manager to replace/add an environ value"""
    old_value = os.environ.get(env_var, None)
    os.environ[env_var] = new_value
    yield
    if old_value is None:
        os.environ.pop(env_var)
    else:
        os.environ[env_var] = old_value


def _id(obj):
    """Return the obj calling the funct."""
    return obj


def skipTest(reason):
    """Unconditionally skip a test."""

    def decorator(test_item):
        """Decorate the test so that it is skipped."""
        if not (isinstance(test_item, type) and
                issubclass(test_item, TestCase)):

            @wraps(test_item)
            def skip_wrapper(*args, **kwargs):
                """Skip a test method raising an exception."""
                raise SkipTest(reason)
            test_item = skip_wrapper

        test_item.skip = reason
        # because the item was skipped, we will make sure that no
        # services are started for it
        if hasattr(test_item, "required_services"):
            test_item.required_services = lambda *args, **kwargs: []

        return test_item

    return decorator


def skipIf(condition, reason):
    """Skip a test if the condition is true."""
    if condition:
        return skipTest(reason)
    return _id


def skipIfOS(current_os, reason):
    """Skip test for a particular os or lists of them."""
    if os:
        if sys.platform in current_os or sys.platform == current_os:
            return skipTest(reason)
        return _id
    return _id


def skipIfNotOS(current_os, reason):
    """Skip test we are not in a particular os."""
    if os:
        if sys.platform not in current_os or \
                sys.platform != current_os:
            return skipTest(reason)
        return _id
    return _id


def skipIfJenkins(current_os, reason):
    """Skip test for a particular os or lists of them
       when running on Jenkins."""
    if os.getenv("JENKINS", False) and (sys.platform in current_os or
                                        sys.platform == current_os):
        return skipTest(reason)
    return _id


class BaseTestCase(TestCase):
    """Base TestCase with helper methods to handle temp dir.

    This class provides:
        mktemp(name): helper to create temporary dirs
        rmtree(path): support read-only shares
        makedirs(path): support read-only shares

    """

    def required_services(self):
        """Return the list of required services for DBusTestCase."""
        return []

    def mktemp(self, name='temp'):
        """Customized mktemp that accepts an optional name argument."""
        tempdir = os.path.join(self.tmpdir, name)
        if os.path.exists(tempdir):
            self.rmtree(tempdir)
        self.makedirs(tempdir)
        return tempdir

    @property
    def tmpdir(self):
        """Default tmpdir: module/class/test_method."""
        # check if we already generated the root path
        root_dir = getattr(self, '__root', None)
        if root_dir:
            return root_dir
        max_filename = 32  # some platforms limit lengths of filenames
        base = os.path.join(self.__class__.__module__[:max_filename],
                            self.__class__.__name__[:max_filename],
                            self._testMethodName[:max_filename])
        # use _trial_temp dir, it should be os.gwtcwd()
        # define the root temp dir of the testcase
        self.__root = os.path.join(os.getcwd(), base)
        return self.__root

    def rmtree(self, path):
        """Custom rmtree that handle ro parent(s) and childs."""
        if not os.path.exists(path):
            return
        # change perms to rw, so we can delete the temp dir
        if path != getattr(self, '__root', None):
            os.chmod(os.path.dirname(path), 0o755)
        if not os.access(path, os.W_OK):
            os.chmod(path, 0o755)
        for dirpath, dirs, files in os.walk(path):
            for dirname in dirs:
                if not os.access(os.path.join(dirpath, dirname), os.W_OK):
                    os.chmod(os.path.join(dirpath, dirname), 0o777)
        shutil.rmtree(path)

    def makedirs(self, path):
        """Custom makedirs that handle ro parent."""
        parent = os.path.dirname(path)
        if os.path.exists(parent):
            os.chmod(parent, 0o755)
        os.makedirs(path)
