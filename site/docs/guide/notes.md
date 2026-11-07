# Notes

Every task carries a note. `space` opens it; `m` opens a pinned scratchpad
note that belongs to no task at all.

![A note](/screenshots/note.svg)

## Two modes

`NORMAL` reads and moves; `INSERT` types. `escape` climbs out one step at a
time — INSERT to NORMAL, NORMAL back to the task.

A note with something in it opens in NORMAL. An empty one opens in INSERT.

The direction keys here, and in the [attachment strip](#attachments), are
whatever the panes move with — `h` `j` `k` `l` under a
[vim layout](/guide/keybindings#vim-layouts).

### NORMAL

| Key | What it does |
| --- | --- |
| `j` / `ö` | Left / right |
| `k` / `l` | Up / down |
| `0` / `$` | Start / end of line |
| `gg` / `G` | Top / bottom |
| `u` / `d` | Half a page up / down |
| `i` | Into INSERT, at the cursor |
| `O` | Open a line below and type on it |
| `o` | Open the link under the cursor |
| `f` | Pick up the [attached files](#attachments) |
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

In NORMAL, `>>` and `<<` do the same, and `3>>` takes three lines. `>` and `<`
also take a motion or a paragraph, whole lines at a time: `>l`, `<G`, `>ip`, `>ap`.
A quoted line nests after its `> `, and numbered lists are counted again.

`enter` at the end of an item opens the next one: a bullet carries its glyph
on, a numbered item the next number (`1.` → `2.`).

`enter` on an empty item walks a list back out: from a nested item it steps
one level up and keeps the marker, and at the top level it takes the marker
away, which is where the list ends.

Numbered lists keep count as they are edited: an item opened or nested in the
middle of one moves the numbers below it along, a nested list starts at `1.`,
and stepping back out picks the outer list up after its last number. A list
keeps the number it was opened with (`5.` counts on from five), and a blank or
unnumbered line ends it.

Lists work inside a quote, nested by the same `tab`, and are drawn in the
quote's green.

Emphasis is held between two marks the page never shows, so the columns in
front of and behind an emphasised phrase are outside it: typing there writes
plain words and `enter` there moves the whole phrase, emphasis and all.
Backspace pressed at the end of one takes the emphasis off and leaves the
words.

## Links

A URL in a note is underlined and shortened when it is drawn; the full address
stays behind it. Markdown links — `[name](url)` — work too. `o` opens the one
under the cursor.

## Attachments

Copy a file in the Finder or in Explorer and press `ctrl+v` in a note. It is
pinned to the strip along the bottom of the note window, inside its frame —
not typed into the note, and not at the cursor: an attachment is something the task *has*, not
something the note says.

Copying the path as text works the same way (`cmd+alt+c` in the Finder,
`ctrl+shift+c` in Explorer), and several files at once land as several
entries. A paste that is anything other than paths is text, and goes in as
text.

When there are more files than fit on a line the strip grows another line and
carries on — nothing is ever counted away or hidden.

`f` hands the keyboard to the strip; the file it is standing on is lit.

| Key | What it does |
| --- | --- |
| `j` / `ö` | Left / right along the strip |
| `k` / `l` | Up / down a row, when there is more than one; `k` off the top row goes back to the text |
| `0` / `$` | The first / last file |
| `enter` | Open it in its application |
| `xx` | Detach it — no question asked, and nothing goes to the Bin |
| `escape` | Back to the text, cursor exactly where it was left |

**The file is never copied.** What the task holds is the path to it, so
attaching costs nothing, one file can be attached to as many tasks as you
like, and moving the file breaks only the way back. When that happens, opening
it says so and offers to detach it.

The pinned note carries files the same way.

## Selecting and copying

`shift` with a motion selects, `ctrl+a` selects everything, and
`ctrl+c` / `ctrl+x` / `ctrl+v` behave as they do in any text field. They work
in both modes; the two that edit take the note into INSERT. The one exception
is a paste that is nothing but file paths, which [attaches](#attachments)
instead of typing them out.

`ctrl+z` / `ctrl+y` undo and redo inside the note.

`ctrl+n`, out on a task row, copies that task's note without opening it.

## The pinned note

![The pinned note](/screenshots/pinned-note.svg)

One note for the whole app, in the same editor — for a thought that is worth
keeping before it is worth filing.
