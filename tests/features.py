"""
Which feature each test module belongs to

A test file in this repo is already one feature's worth of tests, so the
grouping is read off the filename rather than written onto 600 tests by hand.
The root `conftest.py` turns this into a marker per test during collection,
and `tests/test_meta.py` fails if a test file is added without a home here.

Kept in a module of its own rather than in the conftest because
`tests/test_ui/conftest.py` is imported under the bare name `conftest` too,
and whichever of the two lands in `sys.modules` first wins.
"""

FEATURE_BY_MODULE = {
    # tests/test_core
    "test_model": "model",
    "test_todo": "todos",
    "test_project": "projects",
    "test_project_complete": "projects",
    "test_project_color": "colors",
    "test_fixed_projects": "fixed",
    "test_recycle": "recycle",
    "test_history": "undo",
    "test_hooks": "hooks",
    "test_quick_add": "quickadd",
    "test_links": "links",
    "test_files": "notes",
    "test_date_parse": "dates",
    "test_holidays": "dates",
    "test_pinned_note": "notes",
    "test_css_manager": "theming",
    "test_paths": "persistence",
    "test_sync": "persistence",
    # tests/test_ui
    "test_startup": "shell",
    "test_navigation": "shell",
    "test_workflows": "shell",
    "test_help_screen": "help",
    "test_bar": "bar",
    "test_bar_widgets": "bar",
    "test_formatter": "formatters",
    "test_formatter_presets": "formatters",
    "test_project_tree": "projects",
    "test_tree_guides": "projects",
    "test_project_colors": "colors",
    "test_todo_tree": "todos",
    "test_fixed_panes": "fixed",
    "test_undo_redo": "undo",
    "test_quick_add_ui": "quickadd",
    "test_quick_add_complete": "quickadd",
    "test_move_ui": "move",
    "test_move_overrides_sort": "move",
    "test_sort": "sort",
    "test_note_ui": "notes",
    "test_search": "search",
    "test_goto_item": "search",
    "test_calendar": "dates",
    "test_clipboard_links": "links",
    "test_input_cursor": "editing",
    "test_karabiner_keys": "editing",
    "test_key_resolve": "config",
    "test_loader": "config",
}
