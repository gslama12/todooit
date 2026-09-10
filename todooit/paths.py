"""
Resolution of the locations todooit reads and writes.

By default these are the usual platform directories. Setting ``TODOOIT_HOME``
relocates all of them into a single self-contained instance directory::

    $TODOOIT_HOME/
        todooit.db
        cache/          # todooit.tcss + stylesheets/
        config.py

which is how the dev instance (``todooit --dev``) stays isolated from the real
one. Every lookup happens at call time, never at import time, so nothing here
touches the filesystem or freezes a path just because a module was imported.
"""

import os
from pathlib import Path
from typing import Optional

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

MAIN_FOLDER = "todooit"
HOME_ENV_VAR = "TODOOIT_HOME"

DEV_HOME = Path(user_data_dir(f"{MAIN_FOLDER}-dev"))


def instance_home() -> Optional[Path]:
    """The instance directory from ``TODOOIT_HOME``, or None when unset."""

    home = os.environ.get(HOME_ENV_VAR)
    if not home:
        return None

    return Path(os.path.expanduser(home))


def database_file() -> Path:
    if home := instance_home():
        return home / "todooit.db"

    return Path(user_data_dir(MAIN_FOLDER)) / "todooit.db"


def cache_dir() -> Path:
    if home := instance_home():
        return home / "cache"

    return Path(user_cache_dir(MAIN_FOLDER))


def config_file() -> Path:
    if home := instance_home():
        return home / "config.py"

    return Path(user_config_dir(MAIN_FOLDER)) / "config.py"
