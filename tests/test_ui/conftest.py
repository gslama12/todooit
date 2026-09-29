"""
Imported by pytest before any test module in this directory

`todooit.ui.widgets` and `todooit.ui.api` import each other, and the circle only
resolves when the walk into it starts from `todooit.ui.tui`. A test module whose
first todooit import is anything deeper — a bar, a tree — trips the cycle and
poisons the module cache for every file after it. Importing the base module
here settles the import order once, for the whole directory, and makes single
test files runnable on their own.
"""

import tests.test_ui.ui_base  # noqa: F401

import pytest

# Anything a test waits out in real seconds is a race it loses the moment the
# suite runs in parallel and a worker is starved: the notification bar removes
# itself a second after it appears, the note saves itself 0.4s after the last
# keypress. None of that is what any test is checking — the tests that care
# about a flash patch `flash_row` and read off the calls, and a note is stored
# outright when it closes — so the app's own timers are pushed out past the
# life of any test rather than being left to fire in the middle of one.
_FOREVER = 3600.0

# Textual's own machinery (cursor blink, animation) is all well under this,
# and its widgets were written against those timings
_KEEP_BELOW = 0.2


@pytest.fixture(autouse=True)
def _no_wall_clock_waits(monkeypatch):
    from textual.message_pump import MessagePump

    from todooit.ui.screens.note import screen as note_screen
    from todooit.ui.tui import Todooit
    from todooit.ui.widgets.trees.model_tree import ModelTree

    def stretch(original):
        def wrapper(self, interval, *args, **kwargs):
            if interval >= _KEEP_BELOW:
                interval = _FOREVER

            return original(self, interval, *args, **kwargs)

        return wrapper

    # Patched on Todooit rather than on MessagePump so that only what the app
    # itself schedules is stretched. It is also the only way to reach a timer
    # set up in default_config.py, which is exec'd into a fresh namespace on
    # every boot, so patching that module's globals would be thrown away
    # before the first key is pressed.
    monkeypatch.setattr(Todooit, "set_interval", stretch(MessagePump.set_interval))
    monkeypatch.setattr(Todooit, "set_timer", stretch(MessagePump.set_timer))

    # These hang off the note screen and the trees, not off the app
    monkeypatch.setattr(note_screen, "SAVE_DEBOUNCE", _FOREVER)
    monkeypatch.setattr(note_screen, "REPORT_TIMEOUT", _FOREVER)
    monkeypatch.setattr(ModelTree, "FLASH_INTERVAL", _FOREVER)
