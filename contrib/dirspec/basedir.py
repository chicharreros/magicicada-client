# Copyright 2011-2012 Canonical Ltd.
# Copyright 2015-2022 Chicharreros (https://launchpad.net/~chicharreros)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3
# as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""XDG Base Directory paths."""

import os

from dirspec.utils import (
    default_cache_home,
    default_config_home,
    default_config_path,
    default_data_home,
    default_data_path,
    get_env_path,
)


__all__ = [
    'xdg_cache_home',
    'xdg_config_home',
    'xdg_data_home',
    'xdg_config_dirs',
    'xdg_data_dirs',
    'load_config_paths',
    'load_data_paths',
    'load_first_config',
    'save_config_path',
    'save_data_path',
]


def get_xdg_cache_home():
    """Get the path for XDG cache directory in user's HOME."""
    return get_env_path('XDG_CACHE_HOME', default_cache_home)


def get_xdg_config_home():
    """Get the path for XDG config directory in user's HOME."""
    return get_env_path('XDG_CONFIG_HOME', default_config_home)


def get_xdg_data_home():
    """Get the path for XDG data directory in user's HOME."""
    return get_env_path('XDG_DATA_HOME', default_data_home)


def get_xdg_config_dirs():
    """Get the paths for the XDG config directories."""
    result = [get_xdg_config_home()]
    config_dirs = get_env_path('XDG_CONFIG_DIRS', default_config_path)
    result.extend(x for x in config_dirs.split(os.pathsep))
    return result


def get_xdg_data_dirs():
    """Get the paths for the XDG data directories."""
    result = [get_xdg_data_home()]
    data_dirs = get_env_path('XDG_DATA_DIRS', default_data_path)
    result.extend(x for x in data_dirs.split(os.pathsep))
    return result


def load_paths(search_dirs, *resource):
    """Iterator of various paths.

    Return an iterator which gives each directory named 'resource' in the
    search dirs. Information provided by earlier directories should take
    precedence over later ones (ie, the user's config dir comes first).
    """
    resource = os.path.join(*resource)
    assert not resource.startswith('/')
    for target in search_dirs:
        path = os.path.join(target, resource)
        if os.path.exists(path):
            yield path


def load_config_paths(*resource):
    """Iterator of configuration paths.

    Return an iterator which gives each directory named 'resource' in
    the configuration search path. Information provided by earlier
    directories should take precedence over later ones (ie, the user's
    config dir comes first).
    """
    return load_paths(get_xdg_config_dirs(), *resource)


def load_data_paths(*resource):
    """Iterator of data paths.

    Return an iterator which gives each directory named 'resource' in
    the stored data search path. Information provided by earlier
    directories should take precedence over later ones.
    """
    return load_paths(get_xdg_data_dirs(), *resource)


def load_first_config(*resource):
    """Returns the first result from load_config_paths, or None if nothing
    is found to load.
    """
    for path in load_config_paths(*resource):
        return path
    return None


def save_config_path(*resource):
    """Path to save configuration.

    Ensure $XDG_CONFIG_HOME/<resource>/ exists, and return its path.
    'resource' should normally be the name of your application. Use this
    when SAVING configuration settings. Use the xdg_config_dirs variable
    for loading.
    """
    resource = os.path.join(*resource)
    assert not resource.startswith('/')
    path = os.path.join(get_xdg_config_home(), resource)
    if not os.path.isdir(path):
        os.makedirs(path, 0o700)
    return path


def save_data_path(*resource):
    """Path to save data.

    Ensure $XDG_DATA_HOME/<resource>/ exists, and return its path.
    'resource' should normally be the name of your application. Use this
    when STORING a resource. Use the xdg_data_dirs variable for loading.
    """
    resource = os.path.join(*resource)
    assert not resource.startswith('/')
    path = os.path.join(get_xdg_data_home(), resource)
    if not os.path.isdir(path):
        os.makedirs(path, 0o700)
    return path


xdg_cache_home = get_xdg_cache_home()
xdg_config_home = get_xdg_config_home()
xdg_data_home = get_xdg_data_home()

xdg_config_dirs = [x for x in get_xdg_config_dirs() if x]
xdg_data_dirs = [x for x in get_xdg_data_dirs() if x]
