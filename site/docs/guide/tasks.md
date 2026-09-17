# Tasks

The right pane. A row is one task; tasks nest under tasks the same way
projects nest under projects.

## Columns

`Status`, `Description`, `Scheduled`, `Due`, `Agent`, `Recurrence`, `Note`.

The Completed pane swaps the two date columns for the day the task was
finished; the Bin swaps them for the day it was thrown away.

## Adding and editing

| Key | What it does |
| --- | --- |
| `n` | New task, as a sibling |
| `N` | New task, as a child of this one |
| `C` | [Quick add](/guide/quick-add) — a whole task in one line |
| `i` | Edit the description |
| `s` | Edit the scheduled date |
| `d` | Edit the due date |
| `r` | Edit the recurrence |
| `space` | Open the note |
| `enter` | Keep an edit |
| `escape` | Throw an edit away |

A brand new task thrown away without a name is dropped entirely.

## Marking

| Key | What it does |
| --- | --- |
| `c` | Tick the task off (tasks pane only) |
| `p0`–`p3` | Priority: `p1` most urgent, `p3` least, `p0` clears it |
| `a` | Toggle the agent flag |

The status checkbox carries the priority color, so urgency reads from the
first column. A ticked task is struck through and grayed out, and moves to the
[Completed](/guide/projects#completed) pane.

A task with steps under it is ticked off by hand — the last step being done
does not tick it.

::: info The agent flag
An hourglass in a column of its own, for the tasks handed to an AI that is off
working on them. It says nothing about the task being done.
:::

## Moving

| Key | What it does |
| --- | --- |
| `K` / `L` | Move up / down among its siblings |
| `I` | File it under the task above it |
| `U` | Pull it back out one level |
| `M` | Move it to another project (tasks pane only) |

![The move window](/screenshots/move.svg)

`M` opens a one-line prompt that completes project names as you type, the way
a shell completes a filename. See
[Search, move & clipboard](/guide/search-move).

## Links

`o` opens a link. On a task row it opens the first link in the description;
inside a note it opens the one under the cursor. A long URL is shortened when
it is drawn; the address behind it is what gets opened.

## Throwing away

| Key | What it does |
| --- | --- |
| `xx` | Move it to the Bin |
| `u` | Restore it out of the Bin |
| `yy` | Delete it for good (asks first) |
| `YY` | Empty the whole Bin (asks first, and says how much will go) |

See [Undo & the Bin](/guide/undo-bin).
