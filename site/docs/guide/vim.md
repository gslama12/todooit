# Vim editing

Notes are edited with vim's keys, and so are task and project descriptions, to
the extent one line has a use for them. Both share one engine, one search and
one register, so a word yanked in a note pastes into a description.

::: tip `space` `?` lists them all
Inside a note, `space` then `?` opens every key the note knows, grouped by mode
and matching your layout. The keys below are the QWERTZ defaults; the
[vim layouts](/guide/keybindings#vim-layouts) put them back on vim's own.
:::

![The note's keys](/screenshots/note-help.svg)

## Modes

The mode is shown on the note's frame and in the status bar, each in its own
color.

| Mode | Entered with | Left with |
| --- | --- | --- |
| `NORMAL` | — a note always opens here | `escape` closes the note |
| `INSERT` | `i` `a` `I` `A` `o` `O` `gi`, `c` + motion | `escape` |
| `VISUAL` / `V-LINE` | `v` / `V` | `escape`, or the same key again |
| `FLASH` | `s` | a label, `enter` or `escape` |

The panes show `NAV` instead, so it is always clear whether a key moves
between tasks or edits text.

## In a note

### Moving

| Key | What it does |
| --- | --- |
| `j` `ö` `k` `l` | Left, right, up, down |
| `w` `b` `e` | Next word, back a word, end of word |
| `=` / `_` | First non-blank / last character of the line |
| `ü` / `ä` | First non-blank of the line above / below |
| `f` `F` `t` `T` | Find a character forward / back, or up to it |
| `h` / `H` | Repeat the last find / the other way |
| `ctrl+u` / `ctrl+d` | Half a page up / down |
| `gg` / `G` | Top / bottom |
| `{` / `}` | Paragraph up / down |
| `zz` | Centre the cursor line |

A count goes in front of a motion or a command: `3w`, `2dd`, `5>>`. The gutter
shows hybrid line numbers — the cursor line's own, every other line its
distance from it — so a count can be read straight off it.

### Editing

| Key | What it does |
| --- | --- |
| `d` `c` `y` + motion | Delete, change, yank: `dw`, `c$`… `ct.`, `y}` |
| `>` `<` + motion | Nest / unnest lines: `>ip`, `<G` |
| `dd` `D` `x` | Delete the line, to the line end, a character |
| `cc` `C` | Change the line, to the line end |
| `>>` / `<<` | Nest / unnest the line |
| `yy` | Yank the line |
| `p` / `P` | Paste after / before |
| `r` | Replace one character |
| `u` / `ctrl+r` | Undo / redo |

**Text objects** follow an operator or a `v`: `iw` `aw` (word), `iW` `aW`
(WORD), `ip` `ap` (paragraph), and inside / around any pair — `i(` `a[`
`i{` `a<` `i"` `a'` `` i` ``. Either half of a bracket names it.

Yanking writes to the system clipboard, and `p` takes something copied
elsewhere over the last yank, so the register and the desktop never disagree.

### Search, replace & flash

| Key | What it does |
| --- | --- |
| `?` | Search the note (`/` in the vim layouts) |
| `*` | Search for the word under the cursor |
| `n` / `N` | Next / previous match |
| `R` | Replace every match of the last search with what you type |
| `s` | Flash: type a few characters, then the label next to the match |

Flash works like [flash.nvim](https://github.com/folke/flash.nvim): every
match on screen gets a label as you type, nearest first, and typing a label
jumps there. `enter` takes the nearest match. After an operator it is a
motion, so `ds` + target deletes up to it.

### VISUAL and V-LINE

`v` selects by character and `V` by whole line, from the cursor to wherever it
goes next: any motion, a search, a flash jump or a text object.

| Key | What it does |
| --- | --- |
| `y` / `d` / `c` | Yank / delete / change the selection (`x` deletes too) |
| `>` / `<` | Nest the selected lines in / out |
| `p` / `P` | Replace the selection with the register; `P` keeps the register |
| `o` | Go to the other end of the selection |

### INSERT

Typing works as in any text field, plus:

| Key | What it does |
| --- | --- |
| `enter` | New line, carrying a list or quote on |
| `tab` / `shift+tab` | Nest / unnest the line |
| `ctrl+v` | Paste — or [attach](/guide/notes#attachments) a copied file |
| `ctrl+a` | Select all |
| `ctrl+d` | Clear the whole note (asks first) |

### The note window

| Key | What it does |
| --- | --- |
| `gx` | Open the link under the cursor |
| `gf` | Go to the [attached files](/guide/notes#attachments) |
| `escape` | From NORMAL: close the note |
| `space` `?` | List every key |

## Task descriptions

`e` edits a task's or a project's description with the same keys, as far as
one line needs them. It starts in NORMAL on the last character; an empty
description starts in INSERT.

![Changing a word with cw](/screenshots/vim-description.svg)

| Works in a description | |
| --- | --- |
| Motions | `j` `ö`, `w` `b` `e`, `=` `_`, `f` `F` `t` `T` and their repeat |
| Into INSERT | `i` `a` `I` `A` |
| Editing | `d` / `c` + motion or text object, `D` `x`, `cc` `C`, `r`, `p` `P` |
| Text objects | words, WORDs, brackets and quotes |

`enter` keeps the edit from any mode. `escape` goes INSERT → NORMAL, and from
NORMAL keeps the edit and leaves.

There is no yank in a description, so the clipboard only changes when you copy
on purpose. Turn the vim keys off with `api.vim.descriptions = False` and `e`
types straight over the text instead — see
[Configuration](/reference/configuration#vim-keys).

## Changing the keys

The note's keys are set with `api.vim.keys`, apart from the panes' — see
[Configuration](/reference/configuration#vim-keys). The
[vim layouts](/guide/keybindings#vim-layouts) are built that way.
