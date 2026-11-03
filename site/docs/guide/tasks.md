# Tasks

The right pane. A row is one task; tasks nest under tasks the same way
projects nest under projects.

![Tasks nested under tasks, with sub-project blocks below](/screenshots/child-tasks.svg)

## Columns

The status checkbox, `Description`, `Scheduled`, `Due`, `Recurrence`, and the
note icon. The checkbox and note columns go untitled: what they draw says what
they are, so they stay only as wide as that. The two date columns carry their
calendar icon once, in the header, rather than on every row.

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
showing the detail of all of it at once. A folded task shows how many open
steps it hides, e.g. `plan trip (4)`; an unfolded one drops the count.

| Key | What it does |
| --- | --- |
| `N` | Add a step to this task |
| `h` | Fold the task shut, or open it back up |
| `I` | Make this task a step of the one above it |
| `U` | Pull it back out one level |

### A task's day is the earliest its steps start

A task's scheduled date is a floor: none of its steps is planned before it,
but any step may be planned for a later day.

| What you do | What happens |
| --- | --- |
| Add a step to a task that is planned for a day | The step is planned for that day too |
| Plan a task | Steps on its old day move with it; every step that is unplanned or planned earlier moves to that day; steps planned later stay |
| Plan a step for a later day than its task | Allowed; nothing else moves |
| Plan a step before its task | The task, and every task above it still later, moves back to that day |
| Clear a task's day | Steps on its old day lose theirs too; the rest keep theirs |
| Clear a step's day inside a planned task | The step takes the task's day again |
| Tick off a repeating step | It moves to its next day; the task keeps its own |
| Move a task while a step is ticked off | The ticked-off step keeps its day |
| Reopen that step | It moves up to the task's day again, if it is earlier |

Whenever planning one row moves others, the status bar says so, and `ctrl+z` takes
it all back.

### A task's deadline is the latest its steps are due

A task's due date is a ceiling: any step may be due earlier, none later.

| What you do | What happens |
| --- | --- |
| Give a task a due date | Steps due on its old date move with it; every step with no due date or a later one takes it; steps due earlier stay |
| Give a task a due date when a step repeats | The step stops repeating and takes the due date |
| Give a step a due date later than its task's | Refused with a warning; the step keeps its date |
| Clear a task's due date | Steps due on its old date lose theirs too; the rest keep theirs |
| Clear a step's due date inside a task that has one | The step takes the task's due date again |
| Change a task's due date while a step is ticked off | The ticked-off step keeps its due date |
| Reopen that step | Its due date comes down to the task's again, if it is later |

A refusal shows as a warning in the status bar, not an error: it is a rule
holding, and nothing was changed.

### Becoming a step is never refused

A task that becomes a step — added with `N`, or filed under another with `I` —
is fitted to the tasks it now sits inside instead:

| It had | It gets |
| --- | --- |
| No day, or no due date | The task's |
| A day before the task's | The task's day, and so do its own steps planned earlier |
| A due date after the task's | The task's due date, and so do its own steps due later |
| A repeat, under a task that repeats or has a due date | No repeat, and nor does anything under it |

Whatever had to give way is named in the status bar, and one `ctrl+z` takes
back the move and all of it together. Pulling a step back out with `U`, or
moving it to another project, changes nothing but where it sits.

## Marking

| Key | What it does |
| --- | --- |
| `c` | Tick the task off (tasks pane only) |
| `p0`–`p3` | Priority: `p1` most urgent, `p3` least, `p0` clears it |

The status checkbox carries the priority color, so urgency reads from the
first column. A ticked task is struck through and grayed out, and moves to the
[Completed](/guide/projects#completed) pane.

Ticking runs down the tree and un-ticking runs up it: ticking a task ticks
every step under it at every depth, and un-ticking a step hands back every
task it sits inside, since something with work left in it is not finished
however deep that work sits. Un-ticking a task hands back all its steps too.

Ticking a task also ends every recurrence inside it: once the task is done,
none of its steps come back. Un-ticking doesn't restore them — undo (`ctrl+z`) is
the way back from a task ticked by mistake. Ticking a recurring task doesn't
finish it at all; see [Recurrence](/guide/dates#recurrence).

What does *not* happen is the other direction — a task with steps is ticked
off by hand, and its last step being done does not tick it for you.

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
