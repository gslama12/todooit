# Notes

Every task carries a note. `space` opens it; `m` opens a pinned scratchpad
note that belongs to no task at all. A row whose note holds anything — text,
files, or both — shows a note icon in its last column.

![A note](/screenshots/note.svg)

A note opens in NORMAL and is edited with vim's keys — `i` to type, `escape`
back to NORMAL, `escape` again to close it. The keys are on
[Vim editing](/guide/vim); `space` `?` lists them inside the note.

## Markdown

Notes are stored as markdown. Nothing is formatted from a key — write it the
way markdown writes it and it is drawn the moment it is finished. The line
under the cursor shows its raw markdown, so it can be edited as written.

| Typed | Drawn as |
| --- | --- |
| `- ` or `* ` | A bullet |
| `1. ` | A numbered item |
| `> ` | A green quote, wrapping the line |
| `# ` | A heading with a rule under it |
| `---` | A separator |
| `*stars*` | Orange emphasis |
| `[name](url)` | A link, drawn under its name |

### Bullets and numbered lists

- `enter` at the end of an item opens the next one: a bullet carries its glyph
  on, a numbered item the next number (`1.` → `2.`).
- `tab` / `shift+tab` (or `>>` / `<<` in NORMAL) nest a line one level in or
  out. Nested bullets change glyph, and a nested numbered list starts at `1.`.
- `enter` on an empty item walks the list back out: one level up, and at the
  top level it takes the marker away, which ends the list.
- Numbered lists renumber themselves as they are edited: an item opened or nested
  in the middle moves the numbers below it along. A list keeps the
  number it started with (`5.` counts on from five).
- Lists work inside a quote too, drawn in the quote's green.

### Copy and paste

Copying out of a note writes markdown, and markdown pasted in — from a web
page, an editor, another note — is evened out to what a note draws: `__` emphasis
becomes stars, `*` and `+` bullets become `- `, and so on.

`ctrl+n`, out on a task row, copies that task's note without opening it.

## Links

A URL in a note is underlined and shortened when it is drawn; the full address
stays behind it. `gx` opens the one under the cursor (`o` on a task row opens
the first link in its description).

## Attachments

Copy a file in the Finder or in Explorer and press `ctrl+v` in a note (in
INSERT). It is pinned to the strip along the bottom of the note window — not
typed into the note: an attachment is something the task *has*, not something
the note says.

![Files attached to a note](/screenshots/attachments.svg)

Copying the path as text works the same way (`cmd+alt+c` in the Finder,
`ctrl+shift+c` in Explorer), and several files at once land as several
entries. A paste that is anything other than paths goes in as text. When there
are more files than fit on a line the strip grows another line.

`gf` hands the keyboard to the strip; the file it is standing on is lit.

| Key | What it does |
| --- | --- |
| `j` / `ö` | Left / right along the strip (`h` / `l` in the vim layouts) |
| `k` / `l` | Up / down a row; `k` off the top row goes back to the text |
| `enter` | Open it in its application |
| `xx` | Detach it — no question asked, and nothing goes to the Bin |
| `escape` | Back to the text, cursor exactly where it was left |

**The file is never copied.** What the task holds is the path to it, so
attaching costs nothing, one file can be attached to as many tasks as you
like, and moving the file breaks only the way back. When that happens, opening
it says so and offers to detach it.

## Searching notes

The [finder](/guide/search-move#searching-notes) searches every note in the
database when the query starts with `>`, and `enter` opens the note with the
cursor on the hit.

## The pinned note

![The pinned note](/screenshots/pinned-note.svg)

One note for the whole app (`m`), in the same editor and with its own
attachments — for a thought that is worth keeping before it is worth filing.
