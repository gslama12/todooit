# Configuration

The config is a Python file, not a data format. todooit loads
`todooit/utils/default_config.py` first — that is where everything on this page
is really set — and then your own file on top of it, if there is one.

```bash
todooit config-loc     # where yours goes
```

Or point at one directly:

```bash
todooit -c ./my_config.py
```

::: warning
Anything the default config does can be overridden, but nothing it does is
undone for you. Setting a key that is already bound replaces it; the rest of
the default config stays.
:::

## Shape of a config file

The file is executed, then every module-level value is offered to the config
manager. Only functions carrying one of two decorators are hooked up to
anything.

```python
from todooit.ui.api import TodooitAPI, subscribe, timer
from todooit.ui.api.events import Startup

@subscribe(Startup)
def setup(api: TodooitAPI, event):
    api.vars.row_shading = True
```

| Decorator | When it runs |
| --- | --- |
| `@subscribe(Event, ...)` | Every time one of those events fires |
| `@timer(seconds)` | Once immediately, then on that interval |

Events live in `todooit.ui.api.events`: `Startup`, `ShutDown`, `ModeChanged`,
`ProjectSelected`, `TodoSelected`, and the `Spawn*` events the overlays are
opened by. Handlers are called with `(api, event)`. There are no per-field
change events: after every key press the panes redraw from the rows that key
changed, whatever code changed them.

## Keybindings

```python
api.keys.set("x", api.remove_node, group="Editing")
```

| Argument | Meaning |
| --- | --- |
| `keys` | One key, a chord like `"gg"`, `"<ctrl+z>"`, or a list of them |
| `callback` | Usually a `TodooitAPI` method |
| `description` | The help screen text; defaults to the callback's docstring |
| `group` | The help screen section. Sections appear in the order they are first used |
| `hidden` | Keep it working but leave it out of the help screen |
| `label` | Write this in the help screen's key column instead of the key |
| `scope` | `"projects"`, `"todos"`, or omitted for both |

`scope` is what lets one key be a binding over one pane and the start of a
chord over the other — `c` ticks a task off, `c0`–`c9` color a project.

The [Keybindings](/guide/keybindings) page lists every default.

## Columns

```python
from todooit.ui.api.widgets import ProjectWidget, TodoWidget

api.layouts.todo_layout = [
    TodoWidget.status,
    TodoWidget.description,
    TodoWidget.due,
]
api.layouts.project_layout = [
    ProjectWidget.description,
    ProjectWidget.tasks,
]
```

`TodoWidget`: `status`, `description`, `due`, `scheduled`, `completed`,
`binned`, `priority`, `recurrence`, `agent`, `note`. `completed` is only drawn
by the Completed pane and `binned` only by the Bin.

`ProjectWidget`: `description`, `tasks`.

## Formatters

A formatter turns a stored value into what the column draws.

```python
api.formatter.todos.description.add(lambda text, todo: text.upper())
```

Stores: `api.formatter.todos.<field>` for every `TodoWidget` name above,
and `api.formatter.projects.description` / `.tasks`.

Each function is called as `(value, model)`, and is handed `api` as a third
argument if it names one. It returns the new value, or `None` to decline.

Two kinds, and the difference matters:

- **Plain** — the first one that returns something wins, and the rest are
  skipped.
- **`@extra_formatter`** — every one runs, each on the output of the last.

::: tip Order
Formatters run in reverse registration order: **added last runs first**. The
default config relies on this — the graying that completed and binned rows get
is added first so it has the final say.
:::

Ready-made ones live in `todooit.ui.api.formatter_presets`: `agent_icon`,
`description_highlight_link`, `due_danger_today` and `recurrence_icon`.

```python
from todooit.ui.api import extra_formatter

@extra_formatter
def flag_urgent(value, todo, api):
    if todo.priority == 1:
        return f"[{api.vars.theme.red}]{value}[/]"
    return value
```

`add()` returns an id, which `remove()`, `disable()` and `enable()` take.

## Status bar

```python
from todooit.ui.api.bar_widgets import clock, current_project, spacer, text

api.bar.set([
    spacer(width=0),
    current_project(fmt=" 󰉋 {} ", fg=theme.foreground3, bg=theme.background3),
    clock(format="%H:%M", fmt=" 󰥔 {} ", fg=theme.foreground2, bg=theme.background1),
])
```

| Widget | What it shows |
| --- | --- |
| `clock` | The time, on a `strftime` format |
| `current_project` | The project the cursor is in |
| `text` | Fixed text, e.g. a powerline cap glyph |
| `spacer` | Blank, of a given width (`0` fills what is left) |
| `StatusBarWidget` | Whatever a callable of yours returns |

All of them take `fmt`, `fg` and `bg`. The colors are painted under the
value, so markup inside it still wins. `StatusBarWidget(func, width, fmt, fg, bg)`
(from `todooit.ui.widgets.bars`) takes a `func` that must itself carry `@timer`
or `@subscribe`, since that is what decides when the widget is recomputed.

## Theme

One theme ships: `TokyoNight`. Subclass `TodooitThemeBase` to make another.

```python
from todooit.api.theme import TodooitThemeBase

class MyTheme(TodooitThemeBase):
    _name = "mine"
    background1 = "#101010"
    primary = "#89b4fa"

api.css.add_theme(MyTheme)
api.css.set_theme("mine")
```

The fields are `background1`–`background3`, `foreground1`–`foreground3`,
`red`, `orange`, `yellow`, `green`, `blue`, `purple`, `magenta`, `cyan`,
`primary` and `secondary`. Formatters read them off `api.vars.theme`. All of
them but `cyan` are also written out as stylesheet variables (`$primary`, …).

## Settings

`api.vars` holds the handful of switches that are not keys or colors.

| Setting | Default | What it does |
| --- | --- | --- |
| `todo_sort` | `"priority"` | `"priority"`, `"due"`, `"scheduled"` or `None` for filing order |
| `row_shading` | `False` | Tint alternating task rows |
| `always_expand_projects` | `False` | Draw projects expanded |
| `always_expand_todos` | `False` | Draw tasks expanded |
| `show_confirm` | `True` | Ask before a delete that cannot be undone |
