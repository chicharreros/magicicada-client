# -*- coding: utf-8 -*-
#
# Copyright 2011-2012 Canonical Ltd.
# Copyright 2015-2016 Chicharreros (https://launchpad.net/~chicharreros)
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

"""Tests for the proxy-aware webclient."""

TEMPLATE_GSETTINGS_OUTPUT = """\
org.gnome.system.proxy autoconfig-url '{autoconfig_url}'
org.gnome.system.proxy ignore-hosts {ignore_hosts:s}
org.gnome.system.proxy mode '{mode}'
org.gnome.system.proxy.ftp host '{ftp_host}'
org.gnome.system.proxy.ftp port {ftp_port}
org.gnome.system.proxy.http authentication-password '{auth_password}'
org.gnome.system.proxy.http authentication-user '{auth_user}'
org.gnome.system.proxy.http host '{http_host}'
org.gnome.system.proxy.http port {http_port}
org.gnome.system.proxy.http use-authentication {http_use_auth}
org.gnome.system.proxy.https host '{https_host}'
org.gnome.system.proxy.https port {https_port}
org.gnome.system.proxy.socks host '{socks_host}'
org.gnome.system.proxy.socks port {socks_port}
"""

BASE_GSETTINGS_VALUES = {
    "autoconfig_url": "",
    "ignore_hosts": ["localhost", "127.0.0.0/8"],
    "mode": "none",
    "ftp_host": "",
    "ftp_port": 0,
    "auth_password": "",
    "auth_user": "",
    "http_host": "",
    "http_port": 0,
    "http_use_auth": "false",
    "https_host": "",
    "https_port": 0,
    "socks_host": "",
    "socks_port": 0,
}
