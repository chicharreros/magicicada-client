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

"""Tests for the syncdaemon config module."""

import logging
import os
import secrets
import string

from argparse import ArgumentTypeError
from configparser import ConfigParser, NoOptionError
from twisted.internet import defer
from dirspec.basedir import xdg_data_home, xdg_cache_home

from magicicadaclient.testing.testcase import BaseTwistedTestCase
from magicicadaclient import platform
from magicicadaclient.platform import open_file, path_exists
from magicicadaclient.syncdaemon import config


def get_random_string(length=8, alphabet=None):
    if alphabet is None:
        alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))


class BaseConfigTestCase(BaseTwistedTestCase):
    def new_conf_file(self, lines, prefix='test_', suffix='_conf', **kwargs):
        conf_file = os.path.join(
            self.tmpdir, f'{prefix}{get_random_string()}{suffix}.conf'
        )
        if lines is not None:
            # write some throttling values to the config file
            with open_file(conf_file, 'w') as fp:
                fp.write('\n'.join(lines) + '\n' if lines else '')
        return conf_file


class TestConfigBasic(BaseConfigTestCase):
    """Basic _Config object tests."""

    def assertThrottlingSection(self, expected, current, on, read, write):
        """Assert equality for two ConfigParser."""
        self.assertEqual(expected.getboolean(config.THROTTLING, 'on'), on)
        self.assertEqual(
            expected.getint(config.THROTTLING, 'read_limit'), read
        )
        self.assertEqual(
            expected.getint(config.THROTTLING, 'write_limit'), write
        )
        self.assertEqual(
            expected.getboolean(config.THROTTLING, 'on'),
            current.get_throttling(),
        )
        self.assertEqual(
            expected.getint(config.THROTTLING, 'read_limit'),
            current.get_throttling_read_limit(),
        )
        self.assertEqual(
            expected.getint(config.THROTTLING, 'write_limit'),
            current.get_throttling_write_limit(),
        )

    def test_load_missing(self):
        """Test loading the a non-existent config file."""
        conf_file = os.path.join(self.tmpdir, 'test_missing_config.conf')
        # create the config object with a missing config file
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertFalse(conf.get_throttling())
        self.assertEqual(2097152, conf.get_throttling_read_limit())
        self.assertEqual(2097152, conf.get_throttling_write_limit())

    def test_load_empty(self):
        """Test loading the a non-existent config file."""
        conf_file = self.new_conf_file(lines=[])
        # create the config object with an empty config file
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertFalse(conf.get_throttling())
        self.assertEqual(2097152, conf.get_throttling_read_limit())
        self.assertEqual(2097152, conf.get_throttling_write_limit())

    def test_load_basic(self):
        """Test loading the config file with only the throttling values."""
        # write some throttling values to the config file
        conf_file = self.new_conf_file(
            lines=[
                '[bandwidth_throttling]',
                'on = True',
                'read_limit = 1000',
                'write_limit = 200',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_throttling())
        self.assertEqual(1000, conf.get_throttling_read_limit())
        self.assertEqual(200, conf.get_throttling_write_limit())

    def test_load_extra_data(self):
        """Test loading the a config file with other sections too."""
        # write some throttling values to the config file
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'files_sync_enabled = True',
                '',
                '[logging]',
                'level = INFO',
                '',
                '[bandwidth_throttling]',
                'on = True',
                'read_limit = 1000',
                'write_limit = 200',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_throttling())
        self.assertEqual(1000, conf.get_throttling_read_limit())
        self.assertEqual(200, conf.get_throttling_write_limit())

    def test_write_new(self):
        """Test writing the throttling section to a new config file."""
        conf_file = self.new_conf_file(lines=None)
        self.assertFalse(path_exists(conf_file))
        conf = config.SyncDaemonConfigParser(conf_file)
        conf.set_throttling(True)
        conf.set_throttling_read_limit(1000)
        conf.set_throttling_write_limit(100)
        conf.save(conf_file)
        # load the config in a barebone ConfigParser and check
        conf_1 = ConfigParser()
        conf_1.read(conf_file)
        self.assertThrottlingSection(conf_1, conf, True, 1000, 100)

    def test_write_existing(self):
        """Test writing the throttling section to a existing config file."""
        # write some throttling values to the config file
        conf_file = self.new_conf_file(
            lines=[
                '[bandwidth_throttling]',
                'on = False',
                'read_limit = 1000',
                'write_limit = 100',
            ],
        )
        self.assertTrue(path_exists(conf_file))
        conf = config.SyncDaemonConfigParser(conf_file)
        conf.set_throttling(True)
        conf.set_throttling_read_limit(2000)
        conf.set_throttling_write_limit(200)
        conf.save(conf_file)
        # load the config in a barebone ConfigParser and check
        conf_1 = ConfigParser()
        conf_1.read(conf_file)
        self.assertThrottlingSection(conf_1, conf, True, 2000, 200)

    def test_write_extra(self):
        """Writing the throttling back to the file, with extra sections."""
        # write some throttling values to the config file
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'files_sync_enabled = True',
                '',
                '[logging]',
                'level = INFO',
                '',
                '[bandwidth_throttling]',
                'on = False',
                'read_limit = 2000',
                'write_limit = 200',
            ],
        )
        self.assertTrue(path_exists(conf_file))
        conf = config.SyncDaemonConfigParser(conf_file)
        conf.set_throttling(True)
        conf.set_throttling_read_limit(3000)
        conf.set_throttling_write_limit(300)
        conf.save(conf_file)
        # load the config in a barebone ConfigParser and check
        conf_1 = ConfigParser()
        conf_1.read(conf_file)
        self.assertThrottlingSection(conf_1, conf, True, 3000, 300)
        self.assertEqual(
            conf_1.getboolean('__main__', 'files_sync_enabled'),
            conf.get('__main__', 'files_sync_enabled'),
        )
        self.assertEqual(conf_1.get('logging', 'level'), 'INFO')
        self.assertEqual(conf.get('logging', 'level'), 20)

    def test_write_existing_partial(self):
        """Writing a partially updated throttling section to existing file."""
        # write some throttling values to the config file
        conf_file = self.new_conf_file(
            lines=[
                '[bandwidth_throttling]',
                'on = True',
                'read_limit = 1000',
                'write_limit = 100',
            ],
        )
        self.assertTrue(path_exists(conf_file))
        conf = config.SyncDaemonConfigParser(conf_file)
        conf.set_throttling(False)
        conf.save(conf_file)
        # load the config in a barebone ConfigParser and check
        conf_1 = ConfigParser()
        conf_1.read(conf_file)
        self.assertThrottlingSection(conf_1, conf, False, 1000, 100)

    def test_load_negative_limits(self):
        """Test loading the config file with negative read/write limits."""
        # write some throttling values to the config file
        conf_file = self.new_conf_file(
            lines=[
                '[bandwidth_throttling]',
                'on = True',
                'read_limit = -1',
                'write_limit = -1',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_throttling())
        self.assertIsNone(conf.get_throttling_read_limit())
        self.assertIsNone(conf.get_throttling_write_limit())

    def test_load_partial_config(self):
        """Test loading a partial config file and fallback to defaults."""
        # write some throttling values to the config file
        conf_file = self.new_conf_file(
            lines=[
                '[bandwidth_throttling]',
                'on = True',
                'read_limit = 1',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_throttling())
        self.assertEqual(1, conf.get_throttling_read_limit())
        self.assertEqual(2097152, conf.get_throttling_write_limit())

    def test_override(self):
        """Test loading the config file with only the throttling values."""
        # write some throttling values to the config file
        conf_file = self.new_conf_file(
            lines=[
                '[bandwidth_throttling]',
                'on = True',
                'read_limit = 1000',
                'write_limit = 200',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        conf_orig = config.SyncDaemonConfigParser(conf_file)
        overridden_opts = [('bandwidth_throttling', 'on', False)]
        conf.override_options(overridden_opts)
        self.assertFalse(conf.get_throttling())
        self.assertNotEqual(conf.get_throttling(), conf_orig.get_throttling())
        self.assertEqual(1000, conf.get_throttling_read_limit())
        self.assertEqual(200, conf.get_throttling_write_limit())
        conf.save(conf_file)
        # load the config in a barebone ConfigParser and check
        conf_1 = ConfigParser()
        conf_1.read(conf_file)
        self.assertThrottlingSection(conf_1, conf_orig, True, 1000, 200)

    def test_load_udf_autosubscribe(self):
        """Test load/set/override of udf_autosubscribe config value."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'files_sync_enabled = True',
                'udf_autosubscribe = True',
                '',
                '[bandwidth_throttling]',
                'on = True',
                'read_limit = 1000',
                'write_limit = 200',
            ],
        )

        # keep a original around
        conf_orig = config.SyncDaemonConfigParser(conf_file)

        # load the config
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_udf_autosubscribe())
        # change it to False
        conf.set_udf_autosubscribe(False)
        self.assertFalse(conf.get_udf_autosubscribe())
        # save, load and check
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertFalse(conf_1.get_udf_autosubscribe())
        # change it to True
        conf.set_udf_autosubscribe(True)
        self.assertTrue(conf.get_udf_autosubscribe())
        # save, load and check
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf_1.get_udf_autosubscribe())

        # load the config, check the override of the value
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_udf_autosubscribe())
        overridden_opts = [('__main__', 'udf_autosubscribe', False)]
        conf.override_options(overridden_opts)
        self.assertFalse(conf.get_udf_autosubscribe())
        self.assertNotEqual(
            conf.get_udf_autosubscribe(), conf_orig.get_udf_autosubscribe()
        )
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf_1.get_udf_autosubscribe())

    def test_load_share_autosubscribe(self):
        """Test load/set/override of share_autosubscribe config value."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'share_autosubscribe = True',
            ],
        )

        # keep a original around
        conf_orig = config.SyncDaemonConfigParser(conf_file)

        # load the config
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_share_autosubscribe())
        # change it to False
        conf.set_share_autosubscribe(False)
        self.assertFalse(conf.get_share_autosubscribe())
        # save, load and check
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertFalse(conf_1.get_share_autosubscribe())
        # change it to True
        conf.set_share_autosubscribe(True)
        self.assertTrue(conf.get_share_autosubscribe())
        # save, load and check
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf_1.get_share_autosubscribe())

        # load the config, check the override of the value
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_share_autosubscribe())
        overridden_opts = [('__main__', 'share_autosubscribe', False)]
        conf.override_options(overridden_opts)
        self.assertFalse(conf.get_share_autosubscribe())
        self.assertNotEqual(
            conf.get_share_autosubscribe(), conf_orig.get_share_autosubscribe()
        )
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf_1.get_share_autosubscribe())

    def test_load_autoconnect(self):
        """Test load/set/override of autoconnect config value."""
        # ensure that autoconnect is True
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'autoconnect = True',
            ],
        )

        # keep a original around
        conf_orig = config.SyncDaemonConfigParser(conf_file)

        # assert default is correct
        self.assertTrue(
            conf_orig.get_autoconnect(), 'autoconnect is True by default.'
        )

        # load the config
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_autoconnect())

        # change it to False
        conf.set_autoconnect(False)
        self.assertFalse(conf.get_autoconnect())

        # save, load and check
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertFalse(conf_1.get_autoconnect())
        # change it to True
        conf.set_autoconnect(True)
        self.assertTrue(conf.get_autoconnect())
        # save, load and check
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf_1.get_autoconnect())

        # load the config, check the override of the value
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf.get_autoconnect())
        overridden_opts = [('__main__', 'autoconnect', False)]
        conf.override_options(overridden_opts)
        self.assertFalse(conf.get_autoconnect())
        self.assertNotEqual(
            conf.get_autoconnect(), conf_orig.get_autoconnect()
        )
        conf.save(conf_file)
        conf_1 = config.SyncDaemonConfigParser(conf_file)
        self.assertTrue(conf_1.get_autoconnect())

    def test_get_simult_transfers(self):
        """Get simult transfers."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'simult_transfers = 12345',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertEqual(conf.get_simult_transfers(), 12345)

    def test_set_simult_transfers(self):
        """Set simult transfers."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'simult_transfers = 12345',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        conf.set_simult_transfers(666)
        self.assertEqual(conf.get_simult_transfers(), 666)

    def test_get_max_payload_size(self):
        """Get the maximum payload size."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'max_payload_size = 12345',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertEqual(conf.get_max_payload_size(), 12345)

    def test_set_max_payload_size(self):
        """Set the maximum payload size."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'max_payload_size = 12345',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        conf.set_max_payload_size(666)
        self.assertEqual(conf.get_max_payload_size(), 666)

    def test_get_memory_pool_limit(self):
        """Get the memory pool limit."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'memory_pool_limit = 12345',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        self.assertEqual(conf.get_memory_pool_limit(), 12345)

    def test_set_memory_pool_limit(self):
        """Set the memory pool limit."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'memory_pool_limit = 12345',
            ],
        )
        conf = config.SyncDaemonConfigParser(conf_file)
        conf.set_memory_pool_limit(666)
        self.assertEqual(conf.get_memory_pool_limit(), 666)

    def test_get_config_files_path_encoding(self):
        """Check that get_config_files uses paths in the right encoding."""
        temp = self.mktemp()
        fake_path = os.path.join(temp, "Ñandú")
        assert isinstance(fake_path, str)
        os.makedirs(fake_path)
        with open(os.path.join(fake_path, config.CONFIG_FILE), "w") as f:
            f.write("this is a fake config file")
        self.patch(config, "load_config_paths", lambda _: [fake_path])
        config_files = config.get_config_files()
        branch_config = os.path.join(fake_path, config.CONFIG_FILE)
        self.assertIn(branch_config, config_files)

    def test_load_branch_configuration(self):
        """Check that the configuration from the branch is loaded."""
        rootdir = os.environ['ROOTDIR']
        branch_config = os.path.join(rootdir, "data", config.CONFIG_FILE)
        conf_1 = ConfigParser()
        conf_1.read(branch_config)

        conf = config.SyncDaemonConfigParser()

        for section in conf_1.sections():
            parser = value = None
            last_item = None
            for optname in conf_1.options(section):
                optvalue = conf_1.get(section, optname)
                item, subitem = optname.split('.', 1)
                if last_item is None:
                    last_item = item

                if last_item != item:
                    if parser is not None:
                        value = parser(value)
                    self.assertEqual(conf.get(section, last_item), value)
                    parser = value = None
                    last_item = item

                if subitem == 'parser':
                    parser = config.get_parsers()[optvalue]
                elif subitem == 'default':
                    value = optvalue


class ParserBaseTestCase(BaseConfigTestCase):
    parser_name = None

    @property
    def parser(self):
        return config.get_parsers()[self.parser_name]


class ThrottlingLimitParserTests(ParserBaseTestCase):
    parser_name = 'throttling_limit'

    def test_parser(self):
        """Test throttling_limit_parser."""
        good_value = '20480'
        unset_value = '-1'
        bad_value = 'hola'
        invalid_value = None
        zero_value = '0'
        self.assertEqual(20480, self.parser(good_value))
        self.assertIsNone(self.parser(unset_value))
        self.assertRaises(ValueError, self.parser, bad_value)
        self.assertRaises(TypeError, self.parser, invalid_value)
        self.assertIsNone(self.parser(zero_value))


class BooleanParserTests(ParserBaseTestCase):
    parser_name = 'bool'

    def test_true(self):
        for i in ('1', 'yes', 'true', 'on', 'YES', 'Yes', 'True', 'True'):
            with self.subTest(value=i):
                self.assertEqual(self.parser(i), True)

    def test_false(self):
        for i in ('0', 'no', 'false', 'off', 'NO', 'False', 'FALSE', 'OFF'):
            with self.subTest(value=i):
                self.assertEqual(self.parser(i), False)

    def test_error(self):
        for i in (None, 'None', '', object(), [], {}, 0):
            with self.subTest(value=i):
                self.assertRaises(ArgumentTypeError, self.parser, i)

    def test_unparse(self):
        for value in (True, False):
            with self.subTest(value=value):
                result = self.parser.unparse(value)
                self.assertEqual(result, str(value))


class ServerConnectionParserTests(ParserBaseTestCase):
    parser_name = 'connection'

    def test_simple_defaultmode(self):
        results = self.parser('test.host:666')
        self.assertEqual(
            results,
            [
                {
                    'host': 'test.host',
                    'port': 666,
                    'use_ssl': True,
                    'disable_ssl_verify': False,
                }
            ],
        )

    def test_simple_plain(self):
        results = self.parser('test.host:666:plain')
        self.assertEqual(
            results,
            [
                {
                    'host': 'test.host',
                    'port': 666,
                    'use_ssl': False,
                    'disable_ssl_verify': False,
                }
            ],
        )

    def test_simple_ssl(self):
        results = self.parser('test.host:666:ssl')
        self.assertEqual(
            results,
            [
                {
                    'host': 'test.host',
                    'port': 666,
                    'use_ssl': True,
                    'disable_ssl_verify': False,
                }
            ],
        )

    def test_simple_noverify(self):
        results = self.parser('test.host:666:ssl_noverify')
        self.assertEqual(
            results,
            [
                {
                    'host': 'test.host',
                    'port': 666,
                    'use_ssl': True,
                    'disable_ssl_verify': True,
                }
            ],
        )

    def test_simple_bad_mode(self):
        self.assertRaises(
            ArgumentTypeError,
            self.parser,
            'host:666:badmode',
        )

    def test_simple_too_many_parts(self):
        self.assertRaises(
            ArgumentTypeError,
            self.parser,
            'host:666:plain:what',
        )

    def test_simple_too_few_parts(self):
        self.assertRaises(ArgumentTypeError, self.parser, 'test.host')

    def test_simple_port_not_numeric(self):
        self.assertRaises(
            ArgumentTypeError,
            self.parser,
            'test.host:port',
        )

    def test_multiple(self):
        results = self.parser('test.host1:666:plain,host2.com:447')
        self.assertEqual(
            results,
            [
                {
                    'host': 'test.host1',
                    'port': 666,
                    'use_ssl': False,
                    'disable_ssl_verify': False,
                },
                {
                    'host': 'host2.com',
                    'port': 447,
                    'use_ssl': True,
                    'disable_ssl_verify': False,
                },
            ],
        )


class LogLevelParserTests(ParserBaseTestCase):
    parser_name = 'log_level'

    def test_parse(self):
        """Test log_level_parser."""
        good_value = 'INFO'
        bad_value = 'hola'
        invalid_value = None
        self.assertEqual(logging.INFO, self.parser(good_value))
        self.assertEqual(logging.DEBUG, self.parser(bad_value))
        self.assertEqual(logging.DEBUG, self.parser(invalid_value))

    def test_unparse(self):
        for level in ['INFO', 'DEBUG', 'ERROR', 'WARNING']:
            with self.subTest(level=level):
                result = self.parser.unparse(level)
                self.assertEqual(result, getattr(logging, level))


class AuthParserTests(ParserBaseTestCase):
    parser_name = 'auth'

    def test_parse_ok(self):
        cases = [
            ('foo:', 'foo', ''),
            ('foo:bar', 'foo', 'bar'),
            ('foo::::bar', 'foo', ':::bar'),
            ('f:oo::::bar', 'f', 'oo::::bar'),
            ('foo:b:a:r:', 'foo', 'b:a:r:'),
            ('foo:[]{}:!@`?><09', 'foo', '[]{}:!@`?><09'),
        ]
        for value, username, password in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    self.parser(value),
                    {'username': username, 'password': password},
                )

    def test_parse_error(self):
        cases = [
            ':bar',
            ':::bar',
            'foo',
            'foo-bar',
            ':foo:bar',
            None,
            'None',
            '',
            object(),
            [],
            {},
            0,
        ]
        for i in cases:
            with self.subTest(value=i):
                self.assertRaises(ArgumentTypeError, self.parser, i)

    def test_unparse(self):
        cases = [
            (0, 1, '0:1'),
            ('a', 'asdsadsfd', 'a:asdsadsfd'),
            ('', '', ':'),
            (None, {}, 'None:{}'),
        ]
        for username, password, expected in cases:
            with self.subTest(value=expected):
                result = config.AuthParser.unparse(
                    {'username': username, 'password': password}
                )
                self.assertEqual(result, expected)


class LinesParserTests(ParserBaseTestCase):
    parser_name = 'lines'

    def test_parser(self):
        cases = [
            (None, []),
            (0, []),
            ({}, []),
            ([], []),
            ('', []),
            ('     ', []),
            (' \n   \n \n  \n', []),
            (' foo \n   \n bar \n  \n', ['foo', 'bar']),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                result = self.parser(value)
                self.assertEqual(result, expected)

    def test_unparse(self):
        cases = [
            None,
            [],
            ['foo', 'bar', 'baz'],
        ]
        for value in cases:
            with self.subTest(value=value):
                result = self.parser.unparse(value)
                self.assertEqual(result, '\n'.join(value) if value else '')


class XdgHomeParsersTests(ParserBaseTestCase):
    parser_name = 'home_dir'
    good_value = '~/hola/mundo'
    xdg_dir = os.path.join('', 'home', 'fake')

    def test_good_value(self):
        """Test the parser using a good value."""
        homedir = os.path.join('', 'home', 'fake')
        self.patch(platform, 'user_home', homedir)
        expected = os.path.join(self.xdg_dir, 'hola', 'mundo')
        actual = self.parser(self.good_value)
        self.assertEqual(expected, actual)
        self.assertIsInstance(actual, str)
        self.assertNotIsInstance(actual, bytes)

    def test_bad_value(self):
        """Test the parser using a bad value."""
        bad_value = '/../hola'
        with self.assertRaises(OSError) as ctx:
            self.parser(bad_value)

        self.assertEqual(
            str(ctx.exception), "[Errno 1] Operation not permitted: '/..'"
        )

    def test_invalid_value(self):
        """Test the parser using an invalid value."""
        invalid_value = None
        self.assertRaises(AttributeError, self.parser, invalid_value)


class XdgCacheParsersTests(XdgHomeParsersTests):
    parser_name = 'xdg_cache'
    good_value = 'hola/mundo'
    xdg_dir = xdg_cache_home


class XdgDataParsersTests(XdgCacheParsersTests):
    parser_name = 'xdg_data'
    good_value = 'hola/mundo'
    xdg_dir = xdg_data_home


class SyncDaemonConfigParserTests(BaseConfigTestCase):
    """Tests for SyncDaemonConfigParser."""

    @defer.inlineCallbacks
    def setUp(self):
        yield super(SyncDaemonConfigParserTests, self).setUp()
        self.default_config = os.path.join(
            os.environ['ROOTDIR'], 'data', 'syncdaemon.conf'
        )
        self.cp = config.SyncDaemonConfigParser()
        with open(self.default_config) as f:
            self.cp.readfp(f)

    def test_log_level_new_config(self):
        """Test log_level upgrade hook with new config."""
        conf_file = self.new_conf_file(
            lines=[
                '[logging]',
                'level = DEBUG',
            ],
        )
        self.assertTrue(path_exists(conf_file))
        self.cp.read([conf_file])
        self.cp.parse_all()
        self.assertEqual(self.cp.get('logging', 'level'), logging.DEBUG)

    def test_ignore_one(self):
        """Test ignore files config, one regex."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'ignore = .*\\.pyc',  # all .pyc files
            ],
        )
        self.assertTrue(path_exists(conf_file))
        self.cp.read([conf_file])
        self.cp.parse_all()
        self.assertEqual(self.cp.get('__main__', 'ignore'), [r'.*\.pyc'])

    def test_ignore_two(self):
        """Test ignore files config, two regexes."""
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'ignore = .*\\.pyc',  # all .pyc files
                '         .*\\.sw[opnx]',  # all gvim temp files
            ],
        )
        self.assertTrue(path_exists(conf_file))
        self.cp.read([conf_file])
        self.cp.parse_all()
        self.assertEqual(
            self.cp.get('__main__', 'ignore'),
            ['.*\\.pyc', '.*\\.sw[opnx]'],
        )

    def test_fs_monitor_not_default(self):
        """Test get monitor."""
        monitor_id = 'my_monitor'
        conf_file = self.new_conf_file(
            lines=[
                '[__main__]',
                'fs_monitor = %s\n' % monitor_id,
            ],
        )
        self.assertTrue(path_exists(conf_file))
        self.cp.read([conf_file])
        self.cp.parse_all()
        self.assertEqual(self.cp.get('__main__', 'fs_monitor'), monitor_id)

    def test_use_trash_default(self):
        """Test default configuration for use_trash."""
        self.cp.parse_all()
        self.assertEqual(self.cp.get('__main__', 'use_trash'), True)

    def test_ignore_libreoffice_lockfiles(self):
        """Test the default config includes ignoring libreoffice lockfiles."""
        self.cp.parse_all()
        self.assertIn(r'\A\.~lock\..*#\Z', self.cp.get('__main__', 'ignore'))

    def test_simult_transfers(self):
        """Test default configuration for simultaneous transfers."""
        self.cp.parse_all()
        self.assertEqual(self.cp.get('__main__', 'simult_transfers'), 10)

    def test_memory_pool_limit(self):
        """Test default configuration for memory pool limit."""
        self.cp.parse_all()
        configured = self.cp.get('__main__', 'memory_pool_limit')
        self.assertEqual(configured, 200)

    def test_unknown_section_in_defaults(self):
        self.cp.read_string('[foo]\ndebug = True\n')
        configured = self.cp.get('foo', 'debug')
        self.assertEqual(configured, 'True')

    def test_unknown_optname_in_defaults(self):
        self.cp.read_string('[__main__]\nfoo = bar\n')
        configured = self.cp.get('__main__', 'foo')
        self.assertEqual(configured, 'bar')

    def test_unknown_section(self):
        self.cp.read_string('[foo]\ndebug = True\n')
        self.assertRaises(NoOptionError, self.cp.get, 'fooo', 'debug')

    def test_unknown_optname(self):
        self.cp.read_string('[__main__]\nfoo = bar\n')
        self.assertRaises(NoOptionError, self.cp.get, '__main__', 'fooo')


class ConfigglueTestCase(BaseConfigTestCase):
    @defer.inlineCallbacks
    def setUp(self):
        yield super().setUp()
        self.config_defaults = config.SyncDaemonConfigParser().defaults

    def assert_config_correct(self, result, **overrides):
        expected = {
            f'{vv.section}__{vv.name}': vv.value
            for k, v in self.config_defaults.items()
            for kk, vv in v.items()
        }
        expected.update(overrides)

        actual = {
            f'{section}__{optname}': result.get(section, optname)
            for section in result.sections()
            for optname in result.options(section)
        }
        self.assertEqual(sorted(actual.keys()), sorted(expected.keys()))
        for k, v in expected.items():
            self.assertEqual(
                actual[k],
                v,
                f'Mismatch for {k=}, expected {v} but got {actual[k]} '
                'instead.',
            )

    def test_args_empty(self):
        for args in (None, '', (), {}, [], 0):
            with self.subTest(args=args):
                result = config.configglue(args=args)
                self.assert_config_correct(result)

    def test_args_conf_file_stacking_empty_conf(self):
        conf1 = self.new_conf_file(lines=[])
        conf2 = self.new_conf_file(lines=[])
        result = config.configglue(args=[conf1, conf2])
        self.assert_config_correct(result)

    def test_args_conf_file_stacking_non_overlapping_conf(self):
        conf1 = self.new_conf_file(
            prefix='conf1_',
            lines=[
                '[logging]',
                'level = TRACE',
            ],
        )
        conf2 = self.new_conf_file(
            prefix='conf2_',
            lines=[
                '[__main__]',
                'use_trash = False',
            ],
        )
        result = config.configglue(args=[conf1, conf2])
        self.assert_config_correct(
            result,
            logging__level=5,
            __main____use_trash=False,
        )

    def test_args_conf_file_stacking_overlapping_conf(self):
        conf1 = self.new_conf_file(
            prefix='conf1_',
            lines=[
                '[logging]',
                'level = TRACE',
            ],
        )
        conf2 = self.new_conf_file(
            prefix='conf2_',
            lines=[
                '[__main__]',
                'use_trash = False',
                '[logging]',
                'level = ERROR',
            ],
        )
        result = config.configglue(args=[conf1, conf2])
        self.assert_config_correct(
            result,
            logging__level=logging.getLevelName('ERROR'),
            __main____use_trash=False,
        )

    def test_cli_args_override(self):
        result = config.configglue(
            args=[
                '--auth=sapo:pepe',
                '--server=magicicada-server:21101',
                '--logging_level=DEBUG',
                '--debug',
            ]
        )
        self.assert_config_correct(
            result,
            logging__level=logging.getLevelName('DEBUG'),
            __main____auth={'username': 'sapo', 'password': 'pepe'},
            __main____server=[
                {
                    'host': 'magicicada-server',
                    'port': 21101,
                    'use_ssl': True,
                    'disable_ssl_verify': False,
                }
            ],
            __main____debug=True,
        )

    def test_cli_args_override_conf_file(self):
        conf1 = self.new_conf_file(
            prefix='conf1_',
            lines=[
                '[logging]',
                'level = TRACE',
            ],
        )
        conf2 = self.new_conf_file(
            prefix='conf2_',
            lines=[
                '[__main__]',
                'use_trash = False',
                '[logging]',
                'level = ERROR',
            ],
        )
        result = config.configglue(
            args=[
                conf1,
                conf2,
                '--auth=sapo:pepe',
                '--server=magicicada-server:21101',
                '--logging_level=DEBUG',
                '--debug',
            ]
        )
        self.assert_config_correct(
            result,
            logging__level=logging.getLevelName('DEBUG'),
            __main____use_trash=False,
            __main____auth={'username': 'sapo', 'password': 'pepe'},
            __main____server=[
                {
                    'host': 'magicicada-server',
                    'port': 21101,
                    'use_ssl': True,
                    'disable_ssl_verify': False,
                }
            ],
            __main____debug=True,
        )
