from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

from todooit.paths import (
    HOME_ENV_VAR,
    cache_dir,
    config_file,
    database_file,
    instance_home,
)


def test_defaults_to_platform_dirs(monkeypatch):
    monkeypatch.delenv(HOME_ENV_VAR, raising=False)

    assert instance_home() is None
    assert database_file() == Path(user_data_dir("todooit")) / "todooit.db"
    assert cache_dir() == Path(user_cache_dir("todooit"))
    assert config_file() == Path(user_config_dir("todooit")) / "config.py"


def test_instance_home_relocates_everything(monkeypatch, tmp_path):
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path))

    assert instance_home() == tmp_path
    assert database_file() == tmp_path / "todooit.db"
    assert cache_dir() == tmp_path / "cache"
    assert config_file() == tmp_path / "config.py"


def test_empty_instance_home_is_ignored(monkeypatch):
    monkeypatch.setenv(HOME_ENV_VAR, "")

    assert instance_home() is None
    assert database_file() == Path(user_data_dir("todooit")) / "todooit.db"


def test_instance_home_expands_user(monkeypatch):
    monkeypatch.setenv(HOME_ENV_VAR, "~/todooit-dev")

    assert instance_home() == Path.home() / "todooit-dev"


def test_paths_are_not_resolved_at_import_time(monkeypatch, tmp_path):
    """Changing the env after import must still take effect."""

    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path / "first"))
    assert database_file().parent == tmp_path / "first"

    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path / "second"))
    assert database_file().parent == tmp_path / "second"


def test_importing_paths_creates_nothing(monkeypatch, tmp_path):
    import importlib

    import todooit.paths

    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path / "unused"))
    importlib.reload(todooit.paths)

    assert not (tmp_path / "unused").exists()
