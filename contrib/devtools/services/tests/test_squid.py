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

"""Test the squid service."""

import json
import os

from io import BytesIO

from twisted.internet import defer

from devtools.testcases import BaseTestCase
from devtools.services import squid


class PathsTestCase(BaseTestCase):
    """Test the different path functions."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the different tests."""
        yield super(PathsTestCase, self).setUp()
        self.basedir_fn = squid._get_basedir
        self.basedir = self.mktemp('paths')
        self.path_exists = False
        self.created_paths = []
        self.called = []

        def fake_basedir_fn(tempdir):
            """Retun the base dir."""
            self.called.append(('fake_basedir_fn', tempdir))
            return self.basedir

        def fake_makedirs(path):
            """Fake the makedirs function."""
            self.called.append(('fake_makedirs', path))
            self.created_paths.append(path)

        def fake_exists(path):
            """Fake the exists method."""
            self.called.append(('fake_exists', path))
            return path in self.created_paths or self.path_exists

        self.patch(squid, '_get_basedir', fake_basedir_fn)
        self.patch(squid, 'makedirs', fake_makedirs)
        self.patch(squid, 'exists', fake_exists)
        self.patch(squid, 'format_config_path', lambda path: path)

    def test_get_basedir_missing(self):
        """Test the base dir creation."""
        basedir = self.basedir_fn(self.basedir)
        expected_path = os.path.join(self.basedir, squid.SQUID_DIR)
        self.assertEqual(expected_path, basedir)
        self.assertTrue(('fake_makedirs', expected_path) in self.called)
        self.assertTrue(expected_path in self.created_paths)
        self.assertTrue(('fake_exists', expected_path) in self.called)

    def test_get_basedir_present(self):
        """Test the base dir creation."""
        self.path_exists = True
        basedir = self.basedir_fn(self.basedir)
        expected_path = os.path.join(self.basedir, squid.SQUID_DIR)
        self.assertEqual(expected_path, basedir)
        expected_path = os.path.join(self.basedir, squid.SQUID_DIR)
        self.assertTrue(('fake_makedirs', expected_path) not in self.called)
        self.assertTrue(expected_path not in self.created_paths)
        self.assertTrue(('fake_exists', expected_path) in self.called)

    def test_get_spool_temp_path_missing(self):
        """Test the spool path creation."""
        expected_path = os.path.join(self.basedir, squid.SPOOL_DIR)
        result = squid._get_spool_temp_path()
        self.assertEqual(expected_path, result)
        self.assertTrue(('fake_basedir_fn', '') in self.called)
        self.assertTrue(('fake_makedirs', expected_path) in self.called)
        self.assertTrue(expected_path in self.created_paths)
        self.assertTrue(('fake_exists', expected_path) in self.called)

    def test_get_spool_temp_path_present(self):
        """Test the spool path creation."""
        self.path_exists = True
        expected_path = os.path.join(self.basedir, squid.SPOOL_DIR)
        result = squid._get_spool_temp_path()
        self.assertEqual(expected_path, result)
        self.assertTrue(('fake_basedir_fn', '') in self.called)
        self.assertTrue(('fake_makedirs', expected_path) not in self.called)
        self.assertTrue(expected_path not in self.created_paths)
        self.assertTrue(('fake_exists', expected_path) in self.called)

    def test_get_squid_temp_path_missing(self):
        """Test the squid path creation."""
        expected_path = os.path.join(self.basedir, squid.SQUID_DIR, '')
        abspath = os.path.abspath(expected_path)
        result = squid._get_squid_temp_path()
        self.assertEqual(expected_path, result)
        self.assertTrue(('fake_basedir_fn', '') in self.called)
        self.assertTrue(('fake_makedirs', abspath) in self.called)
        self.assertTrue(abspath in self.created_paths)
        self.assertTrue(('fake_exists', abspath) in self.called)

    def test_get_squid_temp_path_present(self):
        """Test the squid path creation."""
        self.path_exists = True
        expected_path = os.path.join(self.basedir, squid.SQUID_DIR, '')
        result = squid._get_squid_temp_path()
        self.assertEqual(expected_path, result)
        self.assertTrue(('fake_basedir_fn', '') in self.called)
        self.assertTrue(('fake_makedirs', expected_path) not in self.called)
        self.assertTrue(expected_path not in self.created_paths)
        self.assertTrue(('fake_exists',
                        os.path.abspath(expected_path)) in self.called)

    def test_get_auth_temp_path(self):
        """Test the creation of the auth path."""
        self.path_exists = False
        expected_path = os.path.join(self.basedir, squid.AUTH_FILE)
        result = squid._get_auth_temp_path()
        self.assertEqual(expected_path, result)
        self.assertTrue(('fake_basedir_fn', '') in self.called)
        self.assertTrue(('fake_makedirs', self.basedir) in self.called)
        self.assertTrue(self.basedir in self.created_paths)
        self.assertTrue(('fake_exists', self.basedir) in self.called)


class EnvironTestCase(BaseTestCase):
    """Test the different environ functions."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the tests."""
        yield super(EnvironTestCase, self).setUp()
        self.called = []
        self.settings = dict(noauth_port=3434, auth_port=232323,
                             username='u1', password='test')

        def fake_dumps(data):
            """Fake dumps."""
            self.called.append(('dumps', data))
            return json.dumps(data)

        def fake_loads(data):
            """Fake loads."""
            self.called.append(('loads', data))
            return json.loads(data)

        self.patch(squid, 'dumps', fake_dumps)
        self.patch(squid, 'loads', fake_loads)
        self.env = {}
        self.old_env = os.environ
        squid.environ = self.env
        self.addCleanup(self.set_back_environ)

    def set_back_environ(self):
        """Set back the env."""
        squid.environ = self.old_env

    def test_store_settings(self):
        """Test the storage of the settings."""
        squid.store_proxy_settings(self.settings)
        self.assertTrue(('dumps', self.settings) in self.called)
        self.assertEqual(self.env[squid.PROXY_ENV_VAR],
                         json.dumps(self.settings))

    def test_retrieve_proxy_settings(self):
        """Test reading the settings."""
        self.env[squid.PROXY_ENV_VAR] = json.dumps(self.settings)
        self.assertTrue(('loads', self.env[squid.PROXY_ENV_VAR]))
        self.assertEqual(squid.retrieve_proxy_settings(), self.settings)

    def test_delete_proxy_settings_present(self):
        """Delete the proxy settings."""
        self.env[squid.PROXY_ENV_VAR] = json.dumps(self.settings)
        squid.delete_proxy_settings()
        self.assertFalse(squid.PROXY_ENV_VAR in self.env)


class SquidRunnerInitTestCase(BaseTestCase):
    """Test the creation of the runner."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the different tests."""
        yield super(SquidRunnerInitTestCase, self).setUp()
        self.executables = {}
        self.called = []

        def fake_find_executable(executable):
            """Fake the find executable."""
            self.called.append(('fake_find_executable', executable))
            return self.executables.get(executable, None)

        self.patch(squid, 'find_executable', fake_find_executable)

    def _assert_missing_binary(self, binary):
        """Perform the assertion when a bin is missing."""
        self.assertRaises(squid.SquidLaunchError, squid.SquidRunner)
        self.assertTrue(('fake_find_executable', binary) in self.called,
                        self.called)

    def test_squid_missing(self):
        """Test when squid is missing."""
        self.executables['htpasswd'] = 'htpasswd'
        self._assert_missing_binary('squid')

    def test_htpasswd_missing(self):
        """Test when htpasswd is missing."""
        self.executables['squid'] = 'squid'
        self.executables['squid3'] = 'squid'
        self._assert_missing_binary('htpasswd')


class Pipe(BytesIO):
    """A read write pipe."""

    def read(self):
        """Read the data."""
        return self.getvalue()


class FakeSubprocess(object):
    """Fake the subprocess module."""

    def __init__(self):
        """Create a new instance."""
        self.called = []
        self.PIPE = 'PIPE'
        self.stdout = Pipe()
        self.stderr = Pipe()

    def Popen(self, args, **kwargs):
        """Fake Popen."""
        self.called.append(('Popen', args, kwargs))
        return self

    def wait(self):
        """Fake wait from a Popen object."""
        self.called.append(('wait',))


class FakeTemplate(object):
    """Fake the string.Template."""

    def __init__(self):
        """Create a new instance."""
        self.data = None
        self.called = []

    def __call__(self, data):
        """Fake constructor."""
        self.data = data
        return self

    def safe_substitute(self, *args, **kwargs):
        """Fake the safe_substitute."""
        self.called.append(('safe_substitute', args, kwargs))
        return self.data


class SquidRunnerTestCase(BaseTestCase):
    """Test the default test case."""

    @defer.inlineCallbacks
    def setUp(self):
        """Set the different tests."""
        yield super(SquidRunnerTestCase, self).setUp()
        self.subprocess = FakeSubprocess()
        self.patch(squid, 'subprocess', self.subprocess)

        self.called = []
        self.executables = dict(squid='squid', htpasswd='htpasswd')

        def fake_find_executable(executable):
            """Fake the find executable."""
            self.called.append(('fake_find_executable', executable))
            return self.executables.get(executable, None)

        self.patch(squid, 'find_executable', fake_find_executable)

        self.auth_temp = 'path/to/auth'

        def fake_get_auth_temp_path(tempdir):
            """Return the path for the auth file."""
            self.called.append(('fake_get_auth_temp_path', tempdir))
            return self.auth_temp

        self.patch(squid, '_get_auth_temp_path', fake_get_auth_temp_path)

        self.port = 2324

        def fake_get_port():
            """Fake the methos that returns the ports."""
            self.called.append(('fake_get_port',))
            return self.port

        self.patch(squid, 'get_arbitrary_port', fake_get_port)
        self.template = FakeTemplate()
        self.patch(squid.string, 'Template', self.template)
        self.runner = squid.SquidRunner()

    def test_generate_swap(self):
        """Test the generation of the squid swap."""
        config_file = 'path/to/config'
        expected_args = ['squid', '-z', '-f', config_file]
        self.runner._generate_swap(config_file)
        self.assertEqual(expected_args, self.subprocess.called[0][1])
        self.assertTrue('wait' in self.subprocess.called[1])

    def test_generate_auth_file(self):
        """Test the generation of the auth file."""
        username = self.runner.settings['username'] = 'mandel'
        password = self.runner.settings['password'] = 'test'
        expected_args = ['htpasswd', '-bc', self.auth_temp,
                         username, password]
        self.patch(squid, 'exists', lambda f: False)
        self.runner._generate_auth_file()
        self.assertEqual(expected_args, self.subprocess.called[0][1])
        self.assertTrue('wait' in self.subprocess.called[1])

    def test_generate_config_file(self):
        """Test the generation of the config file."""
        self.runner.auth_file = self.auth_temp
        self.runner._generate_config_file(self.tmpdir)
        # remove the generated file
        self.addCleanup(os.unlink, self.runner.config_file)
        expected_parameters = \
            ('safe_substitute', (),
             dict(auth_file=self.runner.auth_file,
                  noauth_port_number=self.port,
                  auth_port_number=self.port,
                  spool_temp=squid._get_spool_temp_path(self.tmpdir),
                  squid_temp=squid._get_squid_temp_path(self.tmpdir)))
        self.assertTrue(expected_parameters, self.template.called[0])
        self.assertEqual(2, self.called.count(('fake_get_port',)))

    def test_start_error(self):
        """Test that we do raise an exception correctly."""
        # set the error in the pipes
        out = b'Normal out'
        err = b'Error goes here'
        self.subprocess.stdout.write(out)
        self.subprocess.stderr.write(err)
        for func in ('_generate_auth_file', '_generate_config_file',
                     '_generate_swap'):
            self.patch(self.runner, func, lambda _: None)
        self.patch(squid, 'store_proxy_settings', lambda _: None)
        self.patch(self.runner, '_is_squid_running', lambda: False)
        ex = self.assertRaises(squid.SquidLaunchError,
                               self.runner.start_service)
        # New error that happens in Ubuntu 13.04
        self.assertTrue(any([out in arg.encode("utf8") for arg in ex.args]))
        self.assertTrue(any([err in arg.encode("utf8") for arg in ex.args]))
