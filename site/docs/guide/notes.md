# Notes

Every task carries a note. `space` opens it; `m` opens a pinned scratchpad
note that belongs to no task at all.

![A note](/screenshots/note.svg)

## Two modes

`NORMAL` reads and moves; `INSERT` types. `escape` climbs out one step at a
time — INSERT to NORMAL, NORMAL back to the task.

A note with something in it opens in NORMAL. An empty one opens in INSERT.

### NORMAL

| Key | What it does |
| --- | --- |
| `j` / `ö` | Left / right |
| `k` / `l` | Up / down |
| `0` / `$` | Start / end of line |
| `gg` / `G` | Top / bottom |
| `i` | Into INSERT, at the cursor |
| `O` | Open a line below and type on it |
| `o` | Open the link under the cursor |
| `ctrl+d` | Clear the whole note (asks first) |

## Markup

Nothing is formatted from a key — write it the way markdown writes it and it
is drawn the moment it is finished.

| Typed | Drawn as |
| --- | --- |
| `- ` or `* ` | A bullet |
| `1. ` | A numbered item |
| `> ` | A green quote, wrapping the line |
| `# ` | A heading with a rule under it |
| `---` | A separator |
| `*stars*` | Orange emphasis (the stars themselves take no column) |

`tab` / `shift+tab` nest a line one level in or out. That is the only
keyboard-driven piece of markup, because nesting is the one thing that cannot
be read off the characters on the line.

Lists work inside a quote, nested by the same `tab`, and are drawn in the
quote's green.

## Links

A URL in a note is underlined and shortened when it is drawn; the full address
stays behind it. Markdown links — `[name](url)` — work too. `o` opens the one
under the cursor.

## Selecting and copying

`shift` with a motion selects, `ctrl+a` selects everything, and
`ctrl+c` / `ctrl+x` / `ctrl+v` behave as they do in any text field. They work
in both modes; the two that edit take the note into INSERT.

`ctrl+z` / `ctrl+y` undo and redo inside the note.

`ctrl+n`, out on a task row, copies that task's note without opening it.

## The pinned note

![The pinned note](/screenshots/pinned-note.svg)

One note for the whole app, in the same editor — for a thought that is worth
keeping before it is worth filing.
