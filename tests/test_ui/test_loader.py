import tempfile
from pathlib import Path

from tests.test_ui.ui_base import run_pilot
from todooit.ui.api import loader
from todooit.ui.tui import Todooit


async def test_loader():
    async with run_pilot() as pilot:
        app = pilot.app
        assert isinstance(app, Todooit)
        temp_folder = Path(tempfile.TemporaryDirectory().name)

        incorrect_path = temp_folder / "incorrect_path"
        assert not loader.load_file(app.api.config_manager, incorrect_path)
