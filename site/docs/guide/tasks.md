# Tasks

The right pane. A row is one task; tasks nest under tasks the same way
projects nest under projects.

![Tasks nested under tasks, with sub-project blocks below](/screenshots/child-tasks.svg)

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

## Steps

`N` files a task under the one the cursor is on, and steps nest as deep as you
want them to. `h` folds a task shut again, so a pane can show the work without
showing the detail of all of it at once.

| Key | What it does |
| --- | --- |
| `N` | Add a step to this task |
| `h` | Fold the task shut, or open it back up |
| `I` | Make this task a step of the one above it |
| `U` | Pull it back out one level |

### One day for the whole task

A scheduled date belongs to the task, not to the row it was typed on, and the
app keeps the two ends in step for you:

| What you do | What happens |
| --- | --- |
| Add a step to a task that is planned for a day | The step is planned for that day too |
| Plan a task | Every step of it, at any depth, moves to that day |
| Plan a single step | The step takes the day, and every task it sits inside gives its own day up |

The last one is the useful one: a task whose steps have stopped agreeing on a
day is no longer work that happens all at once, so it stops claiming a day of
its own. Planning the task again puts the whole of it back on one day.

Due dates are yours alone — nothing cascades them.

## Marking

| Key | What it does |
| --- | --- |
| `c` | Tick the task off (tasks pane only) |
| `p0`–`p3` | Priority: `p1` most urgent, `p3` least, `p0` clears it |
| `a` | Toggle the agent flag |

The status checkbox carries the priority color, so urgency reads from the
first column. A ticked task is struck through and grayed out, and moves to the
[Completed](/guide/projects#completed) pane.

Ticking runs down the tree and un-ticking runs up it: ticking a task ticks
every step under it at every depth, and un-ticking a step hands back every
task it sits inside, since something with work left in it is not finished
however deep that work sits.

What does *not* happen is the other direction — a task with steps is ticked
off by hand, and its last step being done does not tick it for you.

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
