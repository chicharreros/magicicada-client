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

"""Utilities for Ubuntu One developer tools."""

import getopt
import sys

from devtools.errors import UsageError

__all__ = ['OptionParser']


def accumulate_list_attr(class_obj, attr, list_obj, base_class=None):
    """Get all of the list attributes of attr from the class hierarchy,
       and return a list of the lists."""
    for base in class_obj.__bases__:
        accumulate_list_attr(base, attr, list_obj)
    if base_class is None or base_class in class_obj.__bases__:
        list_obj.extend(class_obj.__dict__.get(attr, []))


def unpack_padded(length, sequence, default=None):
    """Pads a sequence to length with value of default.

    Returns a list containing the original and padded values.
    """
    newlist = [default] * length
    newlist[:len(sequence)] = list(sequence)
    return newlist


class OptionParser(dict):
    """Base options for our test runner."""

    def __init__(self, *args, **kwargs):
        super(OptionParser, self).__init__(*args, **kwargs)

        # Store info about the options and defaults
        self.long_opts = []
        self.short_opts = ''
        self.docs = {}
        self.defaults = {}
        self.synonyms = {}
        self.dispatch = {}

        # Get the options and defaults
        for _get in [self._get_flags, self._get_params]:
            # We don't use variable 'syns' here. It's just to pad the result.
            (long_opts, short_opts, docs, defaults, syns, dispatch) = _get()
            self.long_opts.extend(long_opts)
            self.short_opts = self.short_opts + short_opts
            self.docs.update(docs)
            self.update(defaults)
            self.defaults.update(defaults)
            self.synonyms.update(syns)
            self.dispatch.update(dispatch)

    # We use some camelcase names for trial compatibility here.
    def parseOptions(self, options=None):
        """Parse the options."""
        if options is None:
            options = sys.argv[1:]

        try:
            opts, args = getopt.getopt(options,
                                       self.short_opts, self.long_opts)
        except getopt.error as e:
            raise UsageError(e)

        for opt, arg in opts:
            if opt[1] == '-':
                opt = opt[2:]
            else:
                opt = opt[1:]

            if (opt not in list(self.synonyms.keys())):
                raise UsageError('No such options: "%s"' % opt)

            opt = self.synonyms[opt]
            if self.defaults[opt] is False:
                self[opt] = True
            else:
                self.dispatch[opt](arg)

        try:
            self.parseArgs(*args)
        except TypeError:
            raise UsageError('Wrong number of arguments.')

        self.postOptions()

    def postOptions(self):
        """Called after options are parsed."""

    def parseArgs(self, *args):
        """Override to handle extra arguments specially."""

    def _parse_arguments(self, arg_type=None, has_default=False):
        """Parse the arguments as either flags or parameters."""
        long_opts, short_opts = [], ''
        docs, defaults, syns, dispatch = {}, {}, {}, {}

        _args = []
        accumulate_list_attr(self.__class__, arg_type, _args)

        for _arg in _args:
            try:
                if has_default:
                    l_opt, s_opt, default, doc, _ = unpack_padded(5, _arg)
                else:
                    default = False
                    l_opt, s_opt, doc, _ = unpack_padded(4, _arg)
            except ValueError:
                raise ValueError('Failed to parse argument: %s' % _arg)
            if not l_opt:
                raise ValueError('An option must have a long name.')

            opt_m_name = 'opt_' + l_opt.replace('-', '_')
            opt_method = getattr(self, opt_m_name, None)
            if opt_method is not None:
                docs[l_opt] = getattr(opt_method, '__doc__', None)
                dispatch[l_opt] = opt_method
                if docs[l_opt] is None:
                    docs[l_opt] = doc
            else:
                docs[l_opt] = doc
                dispatch[l_opt] = lambda arg: True

            defaults[l_opt] = default
            if has_default:
                long_opts.append(l_opt + '=')
            else:
                long_opts.append(l_opt)

            syns[l_opt] = l_opt
            if s_opt is not None:
                short_opts = short_opts + s_opt
                if has_default:
                    short_opts = short_opts + ':'
                syns[s_opt] = l_opt

        return long_opts, short_opts, docs, defaults, syns, dispatch

    def _get_flags(self):
        """Get the flag options."""
        return self._parse_arguments(arg_type='optFlags', has_default=False)

    def _get_params(self):
        """Get the parameters options."""
        return self._parse_arguments(arg_type='optParameters',
                                     has_default=True)
