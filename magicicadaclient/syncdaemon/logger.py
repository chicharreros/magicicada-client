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

"""SyncDaemon logging utilities and config."""

import logging
import sys
import os
import zlib

from magicicadaclient.logger import (
    _DEBUG_LOG_LEVEL,
    CustomRotatingFileHandler,
    DayRotatingFileHandler,
    Logger,
    MultiFilter,
    basic_formatter,
)
# api compatibility imports
from magicicadaclient import logger
from magicicadaclient.platform import (
    get_filesystem_logger,
    setup_filesystem_logging,
)


DebugCapture = logger.DebugCapture
NOTE = logger.NOTE
TRACE = logger.TRACE


class mklog(object):
    """
    Create a logger that keeps track of the method where it's being
    called from, in order to make more informative messages.
    """
    __slots__ = ('logger', 'zipped_desc')

    def __init__(self, _logger, _method, _share, _uid, *args, **kwargs):
        # args are _-prepended to lower the chances of them
        # conflicting with kwargs

        all_args = [repr(a) for a in args]
        all_args.extend("%s=%r" % (k, v) for k, v in kwargs.items())
        args = ", ".join(all_args)

        desc = "%-28s share:%-40r node:%-40r %s(%s) " % (
            _method, _share, _uid, _method, args)
        desc = desc.replace('%', '%%').encode('utf-8')
        self.zipped_desc = zlib.compress(desc, 9)
        self.logger = _logger

    def _log(self, logger_func, *args):
        """Generalized form of the different logging methods."""
        desc = zlib.decompress(self.zipped_desc).decode('utf-8')
        text = desc + args[0]
        logger_func(text, *args[1:])

    def debug(self, *args):
        """Log at level DEBUG"""
        self._log(self.logger.debug, *args)

    def info(self, *args):
        """Log at level INFO"""
        self._log(self.logger.info, *args)

    def warn(self, *args):
        """Log at level WARN"""
        self._log(self.logger.warn, *args)

    def error(self, *args):
        """Log at level ERROR"""
        self._log(self.logger.error, *args)

    def exception(self, *args):
        """Log an exception"""
        self._log(self.logger.exception, *args)

    def note(self, *args):
        """Log at NOTE level (high-priority info) """
        self._log(self.logger.high, *args)

    def trace(self, *args):
        """Log at level TRACE"""
        self._log(self.logger.trace, *args)

    def callbacks(self, success_message='success', success_arg='',
                  failure_message='failure'):
        """
        Return a callback and an errback that log success or failure
        messages.

        The callback/errback pair are pass-throughs; they don't
        interfere in the callback/errback chain of the deferred you
        add them to.
        """
        def callback(arg, success_arg=success_arg):
            "it worked!"
            if callable(success_arg):
                success_arg = success_arg(arg)
            self.debug(success_message, success_arg)
            return arg

        def errback(failure):
            "it failed!"
            self.error(failure_message, failure.getErrorMessage())
            self.debug('traceback follows:\n\n' + failure.getTraceback(), '')
            return failure
        return callback, errback


twisted_logger = logging.getLogger('twisted')
root_logger = logging.getLogger('magicicadaclient')
invnames_logger = logging.getLogger('magicicadaclient.InvalidNames')
brokennodes_logger = logging.getLogger('magicicadaclient.BrokenNodes')
filesystem_logger = get_filesystem_logger()
# now restore our custom logger class
logging.setLoggerClass(Logger)


def configure_handler(handler=None, filename=None, level=_DEBUG_LOG_LEVEL):
    if handler is None:
        handler = CustomRotatingFileHandler(filename=filename)
    handler.addFilter(MultiFilter([root_logger.name, 'twisted', 'pyinotify']))
    handler.setFormatter(basic_formatter)
    handler.setLevel(level)
    return handler


def init(
        base_dir, level=_DEBUG_LOG_LEVEL, max_bytes=2 ** 20, backup_count=5,
        debug=None):
    """Configure logging.

    Set the level to debug of all registered loggers.

    If debug is file, syncdaemon-debug.log is used.
    If it's stdout, all the logging is redirected to stdout.
    If it's stderr, to stderr.

    @param dest: a string with a one or more of 'file', 'stdout', and 'stderr'
        e.g. 'file stdout'

    """
    if debug is None:
        debug = ''

    root_filename = os.path.join(base_dir, 'syncdaemon.log')
    if 'file' in debug:
        # setup the existing loggers in debug
        level = _DEBUG_LOG_LEVEL
        root_filename = os.path.join(base_dir, 'syncdaemon-debug.log')
        # don't cap the file size
        max_bytes = 0

    # root logger
    root_logger.propagate = False
    root_logger.setLevel(level)
    root_handler = configure_handler(filename=root_filename, level=level)
    root_handler.maxBytes = max_bytes
    root_handler.backupCount = backup_count
    root_logger.addHandler(root_handler)

    # add the exception handler to the root logger
    exception_filename = os.path.join(base_dir, 'syncdaemon-exceptions.log')
    exception_handler = configure_handler(
        filename=exception_filename, level=logging.ERROR)
    exception_handler.maxBytes = max_bytes
    exception_handler.backupCount = backup_count
    logging.getLogger('').addHandler(exception_handler)
    root_logger.addHandler(exception_handler)

    # hook twisted.python.log with standard logging
    from twisted.python import log
    observer = log.PythonLoggingObserver('twisted')
    observer.start()
    # configure the logger to only show errors
    twisted_logger.propagate = False
    twisted_logger.setLevel(logging.ERROR)
    twisted_logger.addHandler(root_handler)
    twisted_logger.addHandler(exception_handler)

    for ll in (root_logger, twisted_logger):
        ll.setLevel(_DEBUG_LOG_LEVEL)
        if 'stderr' in debug:
            ll.addHandler(configure_handler(logging.StreamHandler()))
        if 'stdout' in debug:
            ll.addHandler(configure_handler(logging.StreamHandler(sys.stdout)))

    # set the filesystem logging
    setup_filesystem_logging(filesystem_logger, root_handler)

    # invalid filenames log
    invnames_filename = os.path.join(base_dir, 'syncdaemon-invalid-names.log')
    invnames_logger.setLevel(_DEBUG_LOG_LEVEL)
    invnames_logger.addHandler(
        configure_handler(filename=invnames_filename, level=logging.INFO))

    # broken nodes log
    brokennodes_filename = os.path.join(
        base_dir, 'syncdaemon-broken-nodes.log')
    brokennodes_logger.setLevel(_DEBUG_LOG_LEVEL)
    brokennodes_logger.addHandler(
        configure_handler(filename=brokennodes_filename, level=logging.INFO))


def set_server_debug(dest, base_dir):
    """ Set the level to debug of all registered loggers, and replace their
    handlers. if debug_level is file, syncdaemon-debug.log is used. If it's
    stdout, all the logging is redirected to stdout.

    @param dest: a string containing 'file' and/or 'stdout', e.g: 'file stdout'
    """
    SERVER_LOG_LEVEL = 5  # this shows server messages
    logger = logging.getLogger("storage.server")
    logger.setLevel(SERVER_LOG_LEVEL)
    if 'file' in dest:
        filename = os.path.join(base_dir, 'syncdaemon-debug.log')
        logger.addHandler(configure_handler(
            DayRotatingFileHandler(filename=filename), level=SERVER_LOG_LEVEL))
    if 'stdout' in dest:
        logger.addHandler(
            configure_handler(
                logging.StreamHandler(sys.stdout), level=SERVER_LOG_LEVEL))
    if 'stderrt' in dest:
        logger.addHandler(
            configure_handler(logging.StreamHandler(), level=SERVER_LOG_LEVEL))


# configure server logging if SERVER_DEBUG != None
SERVER_DEBUG = os.environ.get("SERVER_DEBUG", None)
if SERVER_DEBUG:
    set_server_debug(SERVER_DEBUG)


def rotate_logs(handlers):
    """Do a rollover of the given handlers."""
    # ignore the missing file error on a failed rollover
    for handler in handlers:
        try:
            handler.doRollover()
        except (AttributeError, OSError):
            pass
