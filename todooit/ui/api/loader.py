import importlib.util
import sys
from typing import TYPE_CHECKING
from pathlib import Path
from contextlib import contextmanager

if TYPE_CHECKING:  # pragma: no cover
    from .plug import ConfigManager


@contextmanager
def temporary_sys_path(path: Path):
    """Temporarily add `path`'s parent directory to sys.path."""

    parent_path = str(path.parent.absolute())
    if parent_path not in sys.path:
        sys.path.insert(0, parent_path)
    try:
        yield
    finally:
        if parent_path in sys.path:
            sys.path.remove(parent_path)


def register(api: "ConfigManager", path: Path) -> None:
    module_name = f"dynamic_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)

    if spec and spec.loader:
        parent_path = str(path.parent.absolute())
        sys.path.append(parent_path)

        with temporary_sys_path(path):
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for obj in vars(module).values():
                api.register(obj)


def load_file(api: "ConfigManager", path: Path) -> bool:
    if not path.exists():
        return False

    if path.suffix == ".py":
        register(api, path)

    return True
