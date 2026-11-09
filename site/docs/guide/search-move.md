# Search, flash & move

## Finder

`/` searches **every task in the database** — not the pane in front — whichever
project it is filed under and whether or not it is still to be done.

![The finder](/screenshots/search.svg)

`enter` walks the cursor over to the task that was picked, in the project it
actually lives in. `escape` leaves everything where it was.

### Searching notes

Start the query with `>` and the finder searches **notes** instead of
descriptions. Every place the word occurs is its own match, shown under its
task with the line it was found on, and `enter` opens the note with the cursor
on that hit.

![The finder searching notes](/screenshots/search-notes.svg)

## Flash

`f` puts a label on every row on screen in the focused pane, where its text
starts. Type the label and the cursor lands on that row — the way to a row you
can see without counting how far away it is. The nearest rows get home-row
keys; when there are more rows than letters, every label is two keys.
`escape` (or any key that is not a label) puts the labels away.

![Flash labels in the tasks pane](/screenshots/flash.svg)

Notes have a flash of their own on `s` — see [Vim editing](/guide/vim#search-replace-flash).
The label letters are set with `api.vars.flash_alphabet`.

## Move

`M`, over a task, asks for one thing: the project to file it under.

![The move window](/screenshots/move.svg)

The whole line is the project name, completed from the first letter the same
way [quick add](/guide/quick-add#project-completion) completes one. Write a
path — `Home/Reading` — when a name on its own is not enough to say which
project is meant.

`K` / `L` shift a row among its siblings, and `I` / `U` indent or unindent it —
tasks and projects alike.

## Clipboard

The system clipboard, so it uses the keys the rest of the desktop uses.

| Key | What it does |
| --- | --- |
| `ctrl+c` | Copy the task's description |
| `ctrl+n` | Copy the task's note, without opening it |
| `ctrl+v` | Paste as a new sibling |

::: info Two channels
Copying writes through the terminal (OSC 52), which carries out of ssh and out
of WSL, and through the host clipboard, which is the only one that can be read
back for a paste.
:::

An error in the status bar can be copied too: click it.

## Jumping

| Key | What it does |
| --- | --- |
| `gg` / `G` | Top / bottom of the pane |
| `f` | Flash to any row on screen |
| `gt` `gu` `gc` `gb` | Today / Upcoming / Completed / Bin |
| `gi` | From a fixed pane, to the task in its own project |
