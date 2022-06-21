# Copyright 2011-2013 Canonical Ltd.
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

"""Utilities for finding and running a squid proxy for testing."""

from __future__ import print_function

import errno
import random
import signal
import string
import subprocess
import sys
import time

from json import dumps, loads
from os import environ, kill, makedirs, unlink
from os.path import abspath, exists, join

from distutils.spawn import find_executable

from devtools.services import (
    find_config_file,
    get_arbitrary_port,
)

NCSA_BASIC_PREFIX = 'basic_'
if sys.platform == 'win32':
    AUTH_PROCESS_PATH = 'C:\\squid\\libexec\\'
    AUTH_PROCESS_NAME = 'ncsa_auth.exe'
    SQUID_START_ARGS = ['-f']
else:
    AUTH_PROCESS_PATH = '/usr/lib/%s/'
    AUTH_PROCESS_NAME = 'ncsa_auth'
    SQUID_START_ARGS = ['-N', '-X', '-f']

SQUID_CONFIG_FILE = 'squid.conf.in'
SQUID_DIR = 'squid'
SPOOL_DIR = 'spool'
AUTH_FILE = 'htpasswd'
PROXY_ENV_VAR = 'SQUID_PROXY_SETTINGS'


def format_config_path(path):
    """Return the path correctly formatted for the config file."""
    # squid cannot handle correctly paths with a single \
    return path.replace('\\', '\\\\')


def get_auth_process_path(squid_version):
    """Return the path to the auth executable."""
    if sys.platform == 'win32':
        path = find_executable('ncsa_auth')
        if path is None:
            path = AUTH_PROCESS_PATH + NCSA_BASIC_PREFIX + AUTH_PROCESS_NAME
            if not exists(path):
                path = AUTH_PROCESS_PATH + AUTH_PROCESS_NAME
        return format_config_path(path)
    else:
        squid = 'squid3' if squid_version == 3 else 'squid'
        auth_path = (AUTH_PROCESS_PATH % squid)
        path = auth_path + NCSA_BASIC_PREFIX + AUTH_PROCESS_NAME
        if not exists(path):
            path = auth_path + AUTH_PROCESS_NAME
        return path


def get_squid_executable():
    """Return the squid executable of the system."""
    # try with squid and if not present try with squid3 for newer systems
    # (Ubuntu P). We also return the path to the auth process so that we can
    # point to the correct one.
    squid = find_executable('squid3')
    version = 3
    if squid is None:
        version = 2
        squid = find_executable('squid')
    auth_process = get_auth_process_path(version)
    return squid, auth_process


def get_htpasswd_executable():
    """Return the htpasswd executable."""
    return find_executable('htpasswd')


def kill_squid(squid_pid):
    """Kill the squid process."""
    if sys.platform == 'win32':
        import win32api
        import win32con

        handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, 0, squid_pid)
        win32api.TerminateProcess(handle, 0)
        win32api.CloseHandle(handle)
    else:
        kill(squid_pid, signal.SIGKILL)


def _make_random_string(count):
    """Make a random string of the given length."""
    entropy = random.SystemRandom()
    return ''.join([entropy.choice(string.letters) for _ in
                   range(count)])


def _get_basedir(tempdir):
    """Return the base squid config."""
    basedir = join(tempdir, SQUID_DIR)
    basedir = abspath(basedir)
    if not exists(basedir):
        makedirs(basedir)
    return basedir


def _get_spool_temp_path(tempdir=''):
    """Return the temp dir to be used for spool."""
    basedir = _get_basedir(tempdir)
    path = join(basedir, SPOOL_DIR)
    path = abspath(path)
    if not exists(path):
        makedirs(path)
    return format_config_path(path)


def _get_squid_temp_path(tempdir=''):
    """Return the temp dir to be used by squid."""
    basedir = _get_basedir(tempdir)
    path = join(basedir, SQUID_DIR)
    path = abspath(path)
    if not exists(path):
        makedirs(path)
    return format_config_path(join(path, ''))


def _get_auth_temp_path(tempdir=''):
    """Return the path for the auth file."""
    basedir = _get_basedir(tempdir)
    auth_file = join(basedir, AUTH_FILE)
    if not exists(basedir):
        makedirs(basedir)
    return format_config_path(auth_file)


def store_proxy_settings(settings):
    """Store the proxy setting in an env var."""
    environ[PROXY_ENV_VAR] = dumps(settings)


def retrieve_proxy_settings():
    """Return the proxy settings of the env."""
    if PROXY_ENV_VAR in environ:
        return loads(environ[PROXY_ENV_VAR])
    return None


def delete_proxy_settings():
    """Delete the proxy env settings."""
    if PROXY_ENV_VAR in environ:
        del environ[PROXY_ENV_VAR]


class SquidLaunchError(Exception):
    """Error while launching squid."""


class SquidRunner(object):
    """Class for running a squid proxy with the local config."""

    def __init__(self):
        """Create a new instance."""
        self.squid, self.auth_process = get_squid_executable()
        if self.squid is None:
            raise SquidLaunchError('Could not locate "squid".')

        self.htpasswd = get_htpasswd_executable()
        if self.htpasswd is None:
            raise SquidLaunchError('Could not locate "htpasswd".')

        self.settings = dict(noauth_port=None, auth_port=None,
                             username=None, password=None)
        self.squid_pid = None
        self.running = False
        self.config_file = None
        self.auth_file = None

    def _generate_config_file(self, tempdir=''):
        """Find the first appropiate squid.conf to use."""
        # load the config file
        path = find_config_file(SQUID_CONFIG_FILE)
        # replace config settings
        basedir = join(tempdir, 'squid')
        basedir = abspath(basedir)
        if not exists(basedir):
            makedirs(basedir)
        self.config_file = join(basedir, 'squid.conf')
        with open(path) as in_file:
            template = string.Template(in_file.read())

        self.settings['noauth_port'] = get_arbitrary_port()
        self.settings['auth_port'] = get_arbitrary_port()
        spool_path = _get_spool_temp_path(tempdir)
        squid_path = _get_squid_temp_path(tempdir)
        with open(self.config_file, 'w') as out_file:
            out_file.write(
                template.safe_substitute(
                    auth_file=self.auth_file,
                    auth_process=self.auth_process,
                    noauth_port_number=self.settings['noauth_port'],
                    auth_port_number=self.settings['auth_port'],
                    spool_temp=spool_path,
                    squid_temp=squid_path))

    def _generate_swap(self, config_file):
        """Generate the squid swap files."""
        squid_args = ['-z', '-f', config_file]
        sp = subprocess.Popen([self.squid] + squid_args,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        sp.wait()

    def _generate_auth_file(self, tempdir=''):
        """Generates a auth file using htpasswd."""
        if self.settings['username'] is None:
            self.settings['username'] = _make_random_string(10)
        if self.settings['password'] is None:
            self.settings['password'] = _make_random_string(10)

        self.auth_file = _get_auth_temp_path(tempdir)
        # remove possible old auth file
        if exists(self.auth_file):
            unlink(self.auth_file)
        # create a new htpasswrd
        htpasswd_args = ['-bc',
                         self.auth_file,
                         self.settings['username'],
                         self.settings['password']]
        sp = subprocess.Popen([self.htpasswd] + htpasswd_args,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        sp.wait()

    def _is_squid_running(self):
        """Return if squid is running."""
        squid_args = ['-k', 'check', '-f', self.config_file]
        print('Starting squid version...')
        message = 'Waiting for squid to start...'
        for timeout in (0.4, 0.1, 0.1, 0.2, 0.5, 1, 3, 5):
            try:
                #  Do not use stdout=PIPE or stderr=PIPE with this function.
                subprocess.check_call([self.squid] + squid_args,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
                return True
            except subprocess.CalledProcessError:
                message += '.'
                print(message)
                time.sleep(timeout)
        return False

    def start_service(self, tempdir=None):
        """Start our own proxy."""
        # generate auth, config and swap dirs
        self._generate_auth_file(tempdir)
        self._generate_config_file(tempdir)
        self._generate_swap(self.config_file)
        squid_args = SQUID_START_ARGS
        squid_args.append(self.config_file)
        sp = subprocess.Popen([self.squid] + squid_args,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        store_proxy_settings(self.settings)
        if not self._is_squid_running():
            # grab the stdout and stderr to provide more information
            output = sp.stdout.read()
            err = sp.stderr.read()
            msg = 'Could not start squid:\nstdout:\n%s\nstderr\n%s' % (
                output, err)
            raise SquidLaunchError(msg)
        self.squid_pid = sp.pid
        self.running = True

    def stop_service(self):
        """Stop our proxy,"""
        try:
            kill_squid(self.squid_pid)
        except OSError as err:
            # If the process already died, ignore the error
            if err.errno == errno.ESRCH:
                pass
            else:
                raise
        delete_proxy_settings()
        self.running = False
        unlink(self.config_file)
        unlink(self.auth_file)
        self.config_file = None
