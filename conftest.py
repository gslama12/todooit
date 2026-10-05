"""
Repo-root conftest: imported before any test module or package conftest

Three things have to happen before the first `import todooit`, and this is the
only file pytest is guaranteed to run that early.
"""

import os
import re
import sys
from pathlib import Path

import pytest

# A plain dict of {test module stem: feature}; imports nothing itself
from tests.features import FEATURE_BY_MODULE

# --------------------------------------------------------------------------
# 1. Textual's idle detector
#
# `textual._wait.wait_for_idle` sleeps SLEEP_GRANULARITY between polls, and
# `App._press_keys` awaits it *twice per keystroke* - so every character a
# test types costs 40ms of asyncio.sleep, whatever the app is doing. Across
# ~300 app boots and ~800 key presses that floor was most of the suite's wall
# clock: 810s, of which only 296s was CPU.
#
# 5ms rather than the 2ms that is fastest single-process: under `-n auto` the
# tighter poll has every worker waking 500x a second, and the box spends its
# time scheduling rather than testing.
import textual._wait as _textual_wait

_IDLE_GRANULARITY = 0.005

assert hasattr(_textual_wait, "SLEEP_GRANULARITY"), (
    "textual._wait.SLEEP_GRANULARITY is gone -- the suite will quietly get "
    "3x slower. Find where textual sleeps between idle polls now."
)

_textual_wait.SLEEP_GRANULARITY = _IDLE_GRANULARITY
_textual_wait.SLEEP_IDLE = _IDLE_GRANULARITY / 20.0


# --------------------------------------------------------------------------
# 2. One todooit instance directory per pytest process
#
# ~/.cache/todooit is written on every single app boot: refresh_css() rewrites
# todooit.tcss, inject_css() drops sheets into stylesheets/, and cleanup()
# rmdir's stylesheets/ outright on shutdown. Under `-n auto` that is several
# processes writing, concatenating and deleting each other's files.
#
# This MUST happen before todooit.ui.tui is imported: `Todooit.CSS_PATH =
# CssManager().css_file` is evaluated at class-definition time and freezes the
# cache path for the whole process. Everything else in todooit/paths.py
# resolves at call time, so module level here is early enough.
assert "todooit" not in sys.modules, (
    "todooit was imported before the rootdir conftest ran; Todooit.CSS_PATH has "
    "already frozen the shared cache path."
)

_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "main")
os.environ["TODOOIT_HOME"] = str(
    Path(os.environ.get("TMPDIR", "/tmp")) / "todooit-tests" / _WORKER
)


def pytest_configure(config):
    """Fail loudly if either of the two guarantees above did not hold"""

    import todooit
    from todooit.ui.tui import Todooit

    # A throwaway venv's editable install points at whichever worktree it was
    # built from, and `python -m pytest` only lands on this one because -m
    # prepends the cwd. Anything that doesn't - a bare `pytest`, a script from
    # elsewhere - silently tests another branch's source against these tests,
    # and the failures look like flakes rather than like the mistake they are.
    assert Path(todooit.__file__).parent.parent == Path(__file__).parent, (
        f"testing {todooit.__file__} against tests from {Path(__file__).parent}"
    )

    worker = getattr(config, "workerinput", {}).get("workerid")
    if worker:
        assert worker in str(Todooit.CSS_PATH), (
            f"worker {worker} froze CSS_PATH at {Todooit.CSS_PATH}; "
            "PYTEST_XDIST_WORKER was not set when conftest.py was imported"
        )

    _check_marker_expression(config)


def _check_marker_expression(config):
    """
    Reject a `-m` expression naming a marker that does not exist

    `--strict-markers` only checks the markers put *on* tests; a typo in the
    expression itself is not an error to pytest, it just quietly matches
    nothing. A run that selects no tests and still reports success is the one
    result worth never showing anyone, because it looks exactly like a run
    that went fine.
    """

    expression = config.option.markexpr
    if not expression:
        return

    known = {line.split(":", 1)[0].strip() for line in config.getini("markers")}
    used = set(re.findall(r"\b[A-Za-z_]\w*\b", expression)) - {"and", "or", "not"}

    unknown = sorted(used - known)
    if unknown:
        raise pytest.UsageError(
            "unknown marker(s) in -m {!r}: {}. Known markers: {}".format(
                expression, ", ".join(unknown), ", ".join(sorted(known))
            )
        )


# --------------------------------------------------------------------------
# 3. Feature markers, derived from the filename
#
# The table lives in tests/features.py (imported at the top) so that
# tests/test_meta.py can read the same one: this file and
# tests/test_ui/conftest.py are both importable under the bare name
# `conftest`, so a test module cannot reliably import from this one.


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    seen_modules = set()

    for item in items:
        stem = item.path.stem

        # layer
        item.add_marker("ui" if "test_ui" in item.path.parts else "core")

        # feature
        if feature := FEATURE_BY_MODULE.get(stem):
            item.add_marker(feature)

        # smoke: the core half is cheap enough to always run, and from each UI
        # module the first test - by convention the one that just proves the
        # feature comes up at all
        if "test_core" in item.path.parts:
            item.add_marker("smoke")
        elif stem not in seen_modules:
            seen_modules.add(stem)
            item.add_marker("smoke")
