# Projects & panes

The left pane holds two kinds of row: the projects you make, and four fixed
ones the app builds from them.

![The projects pane](/screenshots/nested-projects.svg)

## Your projects

| Key | What it does |
| --- | --- |
| `n` | New project, as a sibling |
| `N` | New project, as a child of this one |
| `i` | Rename |
| `h` | Expand / collapse |
| `K` / `L` | Move up / down among its siblings |
| `c0`–`c9` | Color it (the same key again takes the color off) |

Projects nest, and the **Tasks** column counts every todo under a project at
every level. A child project inherits its parent's color; coloring a project
colors everything filed under it.

The ten slots are `c0` red, `c1` blue, `c2` green, `c3` yellow, `c4` orange,
`c5` purple, `c6` cyan, `c7` pink, `c8` brown, `c9` olive.

Projects are not ticked off: `c` only works over the tasks pane.

## The four fixed projects

They cannot be created, renamed, moved or deleted, and they own nothing: what
they show is gathered from your real projects every time they are drawn.

| Key | Pane | What it gathers |
| --- | --- | --- |
| `gt` | Today | Everything scheduled for today or earlier, a block per project |
| `gu` | Upcoming | Everything scheduled from today on, a block per day |
| `gc` | Completed | Every finished task, most recently finished first |
| `gb` | Bin | Everything thrown away and not yet emptied |

Work whose day has already gone by is not dropped: it appears at the top of
today's block, marked as having slipped.

Today and Upcoming list, per block, exactly the work planned for that day. A
task shows only its steps planned for the same day, or stands alone if none
are; a step planned for a later day is listed on that day instead. A step is
always drawn under its whole family line: an ancestor that is part of the
same day's work (in Today, one planned for today or slipped) is an ordinary
row, any other is drawn dimmed, as a context row, just to show where the step
belongs. A task whose steps are spread over the week is a context row on each
of those days.

::: tip Back to where it really lives
`gi`, over a task in one of these panes, walks the cursor to that task in the
project it is actually filed under.
:::

### Upcoming

![The Upcoming pane](/screenshots/upcoming.svg)

Grouped by the day the work is planned for, nearest first. This is the pane
work is rescheduled in.

### Completed

![The Completed pane](/screenshots/completed.svg)

Finishing a task moves it here. Unticking it hands the whole task back to the
project it came from — it was never moved in the database, only shown here
while it was done with.

### Bin

![The Bin](/screenshots/bin.svg)

See [Undo & the Bin](/guide/undo-bin).

## Sorting & view

| Key | What it does |
| --- | --- |
| `SP` / `SD` / `SS` | Sort the tasks by priority / due date / scheduled date |

Tasks are read by priority to begin with. Moving a row by hand drops the pane
out of any sort, so the row stays where you put it. Fixed projects order their
own rows and ignore this.

![Tasks sorted by due date](/screenshots/sort.svg)
