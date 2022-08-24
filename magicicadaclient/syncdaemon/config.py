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

"""SyncDaemon config."""

import argparse
import os
import logging
from collections import defaultdict
from configparser import ConfigParser

from dirspec.basedir import (
    load_config_paths,
    save_config_path,
    xdg_data_home,
    xdg_cache_home,
)

from magicicadaclient.platform import (
    can_write,
    expand_user,
    make_dir,
    path_exists,
    set_dir_readwrite,
)


BASE_FILE_PATH = 'magicicada'
CONFIG_FILE = 'syncdaemon.conf'
BASE_CONFIG_FILE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
        'data',
        CONFIG_FILE,
    )
)
SENTINEL = object()


# sections
MAIN = '__main__'
LOGGING = 'logging'
DEBUG = 'debug'
THROTTLING = 'bandwidth_throttling'
SECTIONS = [MAIN, THROTTLING, LOGGING, DEBUG]

# global logger
logger = logging.getLogger(__name__)

# module private config instance.
# this object is the shared config
_user_config = None


def path_from_unix(path):
    return path.replace('/', os.path.sep)


def make_dir_if_needed(dirpath):
    assert isinstance(dirpath, str)
    if not path_exists(dirpath):
        parent = os.path.dirname(dirpath)
        if path_exists(parent) and not can_write(parent):
            # make the parent dir writable
            set_dir_readwrite(parent)
        make_dir(dirpath, recursive=True)


def unparse_default(value):
    if value is not None:
        value = str(value)
    return value


class Parser:
    """A parser abstraction that can parse and unparse values.

    Useful for defining parsers for config values, specially if the unparsing
    is a non trivial operation.

    """

    def __call__(self, value):
        return value

    def unparse(self, value):
        return unparse_default(value)


def home_dir_parser(value):
    """Parser for the root_dir and shares_dir options.

    Return the path using user home + value.

    """
    path = path_from_unix(value)
    result = expand_user(path)
    make_dir_if_needed(result)
    return result


def xdg_cache_dir_parser(value):
    """Parser for the data_dir option.

    Return the path using xdg_cache_home + value.

    """
    result = os.path.join(xdg_cache_home, path_from_unix(value))
    make_dir_if_needed(result)
    return result


def xdg_data_dir_parser(value):
    """Parser for the data_dir option.

    Return the path using xdg_data_home + value.

    """
    result = os.path.join(xdg_data_home, path_from_unix(value))
    make_dir_if_needed(result)
    return result


class ServerConnectionParser(Parser):
    HOST_SEP = ','
    CONNECTION_SEP = ':'

    def __call__(cls, value):
        """Parser for the server connection info."""
        results = []
        for item in value.split(cls.HOST_SEP):
            ci_parts = item.split(cls.CONNECTION_SEP)
            if len(ci_parts) == 2:
                host, port = ci_parts
                mode = 'ssl'  # default
            elif len(ci_parts) == 3:
                host, port, mode = ci_parts
            else:
                raise argparse.ArgumentTypeError(
                    "connection string must be HOST:PORT or HOST:PORT:SSL_MODE"
                )

            if mode == 'plain':
                use_ssl = False
                disable_ssl_verify = False
            elif mode == 'ssl':
                use_ssl = True
                disable_ssl_verify = False
            elif mode == 'ssl_noverify':
                use_ssl = True
                disable_ssl_verify = True
            else:
                raise argparse.ArgumentTypeError(
                    "SSL mode (from HOST:PORT:SSL_MODE) accepts only the "
                    "following options: 'plain', 'ssl', 'ssl_noverify'"
                )

            try:
                port = int(port)
            except ValueError:
                raise argparse.ArgumentTypeError(
                    "Port (from HOST:PORT:SSL_MODE) should be an integer value"
                )

            results.append(
                {
                    'host': host,
                    'port': port,
                    'use_ssl': use_ssl,
                    'disable_ssl_verify': disable_ssl_verify,
                }
            )
        return results

    @classmethod
    def unparse_one_host(cls, value):
        use_ssl = value.pop('use_ssl')
        disable_ssl_verify = value.pop('disable_ssl_verify')
        if use_ssl and disable_ssl_verify:
            mode = 'ssl_noverify'
        elif use_ssl and not disable_ssl_verify:
            mode = 'ssl'
        else:
            mode = 'plain'
        return '{host}{sep}{port}{sep}{mode}'.format(
            **value, mode=mode, sep=cls.CONNECTION_SEP
        )

    @classmethod
    def unparse(cls, value):
        return cls.HOST_SEP.join(cls.unparse_one_host(host) for host in value)


server_connection_parser = ServerConnectionParser()


class LogLevelParser(Parser):
    def __call__(self, value):
        """Parser for "logging" module log levels.

        The logging API sucks big time, the only way to trustworthy find if the
        log level is defined is to check the private attribute.
        """
        try:
            level = logging._nameToLevel[value]
        except KeyError:
            # if level don't exists in our custom levels, fallback to DEBUG
            level = logging.DEBUG
        return level

    @classmethod
    def unparse(cls, value):
        return logging.getLevelName(value)


log_level_parser = LogLevelParser()


def throttling_limit_parser(value):
    """Parser for throttling limit values, if value <= 0 returns None"""
    value = int(value)
    if value <= 0:
        return None
    else:
        return value


class AuthParser(Parser):
    def __call__(self, value):
        values = []
        if isinstance(value, str):
            # check if we have auth credentials
            values = value.split(':', 1)
        if len(values) != 2 or not values[0]:
            raise argparse.ArgumentTypeError(
                "%r is not of the form USERNAME:PASSWORD" % value
            )

        return dict(zip(('username', 'password'), values))

    @classmethod
    def unparse(cls, value):
        return '{username}:{password}'.format(**value)


class BooleanParser(Parser):
    """Taken from https://docs.python.org/3/library/configparser.html.

    A convenience method which coerces the value to a Boolean value. Note that
    the accepted values for the option are '1', 'yes', 'true', and 'on', which
    cause this method to return True, and '0', 'no', 'false', and 'off', which
    cause it to return False. These string values are checked in a
    case-insensitive manner. Any other value will cause it to raise ValueError.

    """

    def __call__(self, value):
        value = getattr(value, 'lower', lambda: None)()
        if value in ('1', 'yes', 'true', 'on'):
            result = True
        elif value in ('0', 'no', 'false', 'off'):
            result = False
        else:
            raise argparse.ArgumentTypeError(
                '%r is not a valid boolean-like value.' % value
            )
        return result


boolean_parser = BooleanParser()


class LinesParser(Parser):
    def __call__(self, value):
        result = []
        if value:
            result = [i.strip() for i in value.split() if i.strip()]
        return result

    @classmethod
    def unparse(cls, value):
        return '\n'.join(value or [])


def get_parsers():
    """Return a list of tuples: (name, parser)."""
    return dict(
        (
            ('auth', AuthParser()),
            ('bool', boolean_parser),
            ('connection', ServerConnectionParser()),
            ('int', int),
            ('home_dir', home_dir_parser),
            ('lines', LinesParser()),
            ('log_level', LogLevelParser()),
            ('throttling_limit', throttling_limit_parser),
            ('xdg_cache', xdg_cache_dir_parser),
            ('xdg_data', xdg_data_dir_parser),
        )
    )


def get_config_files():
    """Return the path to the config files or an empty list.

    The search path is based on the paths returned by load_config_paths
    but it's returned in reverse order (e.g: /etc/xdg first).

    """
    # get (and possibly create if don't exists) the user config file
    _user_config_path = os.path.join(
        save_config_path(BASE_FILE_PATH), CONFIG_FILE
    )
    config_files = [_user_config_path]
    for xdg_config_dir in load_config_paths(BASE_FILE_PATH):
        config_file = os.path.join(xdg_config_dir, CONFIG_FILE)
        if os.path.exists(config_file) and config_file not in config_files:
            config_files.append(config_file)

    # reverse the list as load_config_paths returns the user dir first
    config_files.reverse()

    return config_files


def get_user_config(config_files=None, force_reload=False):
    """Return the singleton SyncDaemonConfigParser instance."""
    global _user_config
    if _user_config is None or force_reload:
        if config_files is None:
            config_files = get_config_files()
        _user_config = SyncDaemonConfigParser(*config_files)
    return _user_config


class _StoreTrueAction(argparse.Action):
    """Re-implement from upstream.

    https://github.com/python/cpython/issues/96220

    """

    def __init__(
        self,
        option_strings,
        dest,
        default=False,
        type=boolean_parser,
        required=False,
        help=None,
        metavar=None,
    ):
        super(_StoreTrueAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=0,
            const=True,
            default=default,
            type=type,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, self.const)


class SyncDaemonConfigOption:
    ARGPARSE_SECTION_SEP = '_'

    def __init__(self, section, name):
        super().__init__()
        self.section = section
        self.name = name
        self.parsed_value = None
        self.attrs = {}

    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        return str(self.__dict__)

    def add_option(self, key, value):
        self.attrs[key] = value

    def parse(self, value):
        return self.parser(value) if self.parser else value

    def unparse(self, value):
        parser = getattr(self.parser, 'unparse', unparse_default)
        return parser(value) if parser else value

    @property
    def parser(self):
        parser_name = self.attrs.get('parser')
        _parser = get_parsers().get(parser_name)
        return getattr(_parser, 'parse', _parser)

    @property
    def raw_value(self):
        return self.attrs.get('raw', self.default)

    @property
    def default(self):
        return self.attrs.get('default')

    @property
    def value(self):
        if self.parsed_value is not None:
            return self.parsed_value

        value = self.default if self.raw_value is None else self.raw_value
        self.parsed_value = self.parse(value)
        return self.parsed_value

    @property
    def is_empty(self):
        return not bool(self.default)

    @property
    def argparse_name(self):
        if self.section == MAIN:
            result = self.name
        else:
            result = f'{self.section}{self.ARGPARSE_SECTION_SEP}{self.name}'
        return result.lower()

    @property
    def argparse_flag(self):
        """Return the argparse flag name for this option.

        name or flags - Either a name or a list of option strings, e.g. foo or
        -f, --foo.

        """
        return '--' + self.argparse_name

    def argparse_data(self):
        """Return argparse's add_argument suitable kwargs, following the doc.

        action - The basic type of action to be taken when this argument is
        encountered at the command line.

        nargs - The number of command-line arguments that should be consumed.

        const - A constant value required by some action and nargs selections.

        default - The value produced if the argument is absent from the command
        line.

        type - The type to which the command-line argument should be converted.

        choices - A container of the allowable values for the argument.

        required - Whether or not the command-line option may be omitted
        (optionals only).

        help - A brief description of what the argument does.

        metavar - A name for the argument in usage messages.

        dest - The name of the attribute to be added to the object returned by
        parse_args().

        """
        result = {}

        help_text = self.attrs.get('help')
        # format help message, if needed
        if help_text:
            help_text %= self.attrs
            result['help'] = help_text

        action = self.attrs.get('action')
        if action == 'store_true':
            result['action'] = _StoreTrueAction
        elif action is not None:
            result['action'] = action

        metavar = self.attrs.get('metavar')
        if metavar is not None:
            result['metavar'] = metavar

        # define converters using this item's parser
        # `type` can take any callable that takes a single string argument and
        # returns the converted value
        if self.parser is not None:
            result['type'] = self.parser

        # `default` specifies what value should be used if the command-line
        # argument is not present.
        if self.default is not None:
            result['default'] = self.default
        else:
            result.pop('default', None)

        return result


def config_parser_as_dict(parser):
    result = defaultdict(dict)
    # regroup options by prefix
    for section in parser.sections():
        for optname in parser.options(section):
            value = parser.get(section, optname)
            assert '.' in optname, optname
            if '.' in optname:
                item, subitem = optname.split('.', 1)
            if item not in result[section]:
                result[section][item] = SyncDaemonConfigOption(section, item)
            result[section][item].add_option(subitem, value)
    return result


def base_config_as_dict():
    base_parser = ConfigParser()
    assert os.path.exists(BASE_CONFIG_FILE)
    base_parser.read(BASE_CONFIG_FILE)
    return config_parser_as_dict(base_parser)


class SyncDaemonConfigParser(ConfigParser):
    """Custom ConfigParser with syncdaemon parsers.

    Config object to read/write config values from/to the user config file.
    Most of the methods in this class aren't thread-safe.

    """

    def __init__(self, *filenames, **kwargs):
        # get the base/template config files
        self.defaults = base_config_as_dict()
        super().__init__(**kwargs)
        self.filenames = list(filenames)
        self.read(self.filenames)  # XXX

    def parse_all(self):
        self.read(self.filenames)

    def save(self, config_file=None):
        """Save the config object to disk."""
        if config_file is None:
            config_file = self.filenames[0]  # XXX: IndexError if no filenames
        # cleanup empty sections
        for section in SECTIONS:
            if self.has_section(section) and not self.options(section):
                self.remove_section(section)
        with open(config_file + '.new', 'w') as fp:
            self.write(fp)
        if os.path.exists(config_file):
            os.rename(config_file, config_file + '.old')
        os.rename(config_file + '.new', config_file)

    def override_options_from_args(self, args):
        """Merge in the values provided by the overridden options from args."""
        return  # XXX
        control = defaultdict(dict)  # XXX: to be removed when tests are added
        for section, values in self.items():
            for optname, option in values.items():
                argvalue = getattr(args, option.argparse_name)
                self.set(section, optname, argvalue)
                control[section][optname] = argvalue
        return control

    def override_options(self, overridden_options):
        """Merge in the values provided by the overridden_options."""
        for section, optname, optvalue in overridden_options:
            self.set(section, optname, optvalue)

    def get(self, section, option, **kwargs):
        if not self.has_section(section):
            self.add_section(section)
        default = self.defaults[section].get(option, SENTINEL)
        if default is not SENTINEL:
            kwargs.setdefault('fallback', default.raw_value)
        result = unparsed = super().get(section, option, **kwargs)
        if default is not SENTINEL:
            result = default.parse(unparsed)
        return result

    def set(self, section, option, value):
        if not self.has_section(section):
            self.add_section(section)
        default = self.defaults[section][option]
        super().set(section, option, default.unparse(value))

    # throttling section get/set
    def set_throttling(self, enabled):
        self.set(THROTTLING, 'on', enabled)

    def set_throttling_read_limit(self, bytes):
        self.set(THROTTLING, 'read_limit', str(bytes))

    def set_throttling_write_limit(self, bytes):
        self.set(THROTTLING, 'write_limit', str(bytes))

    def get_throttling(self):
        return self.get(THROTTLING, 'on')

    def get_throttling_read_limit(self):
        return self.get(THROTTLING, 'read_limit')

    def get_throttling_write_limit(self):
        return self.get(THROTTLING, 'write_limit')

    def set_udf_autosubscribe(self, enabled):
        self.set(MAIN, 'udf_autosubscribe', enabled)

    def get_udf_autosubscribe(self):
        return self.get(MAIN, 'udf_autosubscribe')

    def set_share_autosubscribe(self, enabled):
        self.set(MAIN, 'share_autosubscribe', enabled)

    def get_share_autosubscribe(self):
        return self.get(MAIN, 'share_autosubscribe')

    # files sync enablement get/set
    def set_files_sync_enabled(self, enabled):
        self.set(MAIN, 'files_sync_enabled', enabled)

    def get_files_sync_enabled(self):
        return self.get(MAIN, 'files_sync_enabled')

    def set_autoconnect(self, enabled):
        self.set(MAIN, 'autoconnect', enabled)

    def get_autoconnect(self):
        return self.get(MAIN, 'autoconnect')

    def get_use_trash(self):
        return self.get(MAIN, 'use_trash')

    def set_use_trash(self, enabled):
        self.set(MAIN, 'use_trash', enabled)

    def get_simult_transfers(self):
        """Get the simultaneous transfers value."""
        return self.get(MAIN, 'simult_transfers')

    def set_simult_transfers(self, value):
        """Set the simultaneous transfers value."""
        self.set(MAIN, 'simult_transfers', value)

    def get_max_payload_size(self):
        """Get the maximum payload size."""
        return self.get(MAIN, 'max_payload_size')

    def set_max_payload_size(self, value):
        """Set the maximum payload size."""
        self.set(MAIN, 'max_payload_size', value)

    def get_memory_pool_limit(self):
        """Get the memory pool limit."""
        return self.get(MAIN, 'memory_pool_limit')

    def set_memory_pool_limit(self, value):
        """Set the memory pool limit."""
        self.set(MAIN, 'memory_pool_limit', value)


def configglue(args):
    """Parse arguments with options and defaults taken from config files.

    @param args: arguments to be parsed.

    """
    existing_config_files = get_config_files()
    # Parse any conf_file specification
    # Set add_help=False so that it doesn't parse -h and print incomplete help.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        'conf_file',
        nargs='*',
        default=existing_config_files,
        type=argparse.FileType('r'),
        help=(
            'Zero or more config files, the leftist file has precedence over '
            'those to its right.'
        ),
    )
    parsed_args, remaining_args = parser.parse_known_args(args or [])

    filenames = existing_config_files + parsed_args.conf_file
    config = get_user_config(config_files=filenames)

    # Configure and parse the rest of arguments
    # Don't suppress add_help here so it properly handles -h
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        # Inherit options from previous parser
        parents=[parser],
    )

    for section, values in config.defaults.items():
        if section == MAIN:
            group_parser = parser
        else:
            group_parser = parser.add_argument_group(section)
        for optname, option in values.items():
            group_parser.add_argument(
                option.argparse_flag, **option.argparse_data()
            )

    final_args = parser.parse_args(remaining_args)

    # XXX: return current config which should have the overriden values set
    # (but not stored in file)
    return final_args
