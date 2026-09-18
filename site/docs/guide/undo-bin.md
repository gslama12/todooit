# Undo & the Bin

## The Bin

`xx` throws a task or project away. Nothing asks, because nothing is lost:

| Key | What it does |
| --- | --- |
| `xx` | To the Bin |
| `u` | Back out of the Bin, into the project it came from |
| `yy` | Delete for good (asks first) |
| `YY` | Empty the whole Bin (asks first, and counts what will go) |

![The Bin](/screenshots/bin.svg)

![Deleting for good asks first](/screenshots/confirm.svg)

A task arrives whole, with its steps under it, and goes back out whole. It
stays in the Bin until it is restored or deleted for good — nothing expires on
its own.

Dropping a project scatters its work into the Bin along with it.

The Bin pane shows the project each row came out of and the day it landed
there, instead of the dates it was working to.

## Undo and redo

| Key | What it does |
| --- | --- |
| `ctrl+z` | Take back the last change |
| `ctrl+y` | Put it back |

Every edit either pane can make: a rename, a priority, a task binned, a task
deleted for good, a whole project dropped with its work scattered. One key at
a time, however much of the tree that key moved — a key that moved half the
tree comes back whole.

::: info Not vim's `u`
`u` is the key that fetches a task back out of the Bin, and it was here first.
Undo is on the keys the rest of the desktop uses, which is also what the note
window answers to.
:::

Rows that arrive from somewhere else — another todooit writing to the same
database — are not a change made here, so they are not folded into what
`ctrl+z` would take back.
