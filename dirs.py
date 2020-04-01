import os
import platform
import appdirs

_author = 'test'
_appname = 'simple_editor'

cachedir = appdirs.user_cache_dir(_appname, _author)
configdir = appdirs.user_config_dir(_appname, _author)
installdir = os.path.dirname(os.path.abspath(__file__))

def makedirs():
    all_paths = [cachedir, configdir]
    for path in all_paths:
        os.makedirs(path, exist_ok=True)
