# 05: Engine tracer: left, right, up, down through the engine

**What to build:** A new pure engine package drives the note's basic movement end to end through a buffer interface, a note adapter and a configurable keymap. This proves the architecture with the smallest useful set of keys.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] The engine package has no Textual imports, takes key strings, and acts through a buffer interface
- [ ] Line-only commands can be switched off by the host, ready for a later single-line host
- [ ] The note adapter implements the buffer interface and routes NORMAL keys to the engine
- [ ] `api.vim.keys` offers `set` and `remap` in the style of `api.keys`, with commands named by enums
- [ ] Defaults are set in the default config, and `j ö k l` move through the engine
- [ ] Remapping a key in config changes what the note does
- [ ] The note editor no longer follows the panes' direction keys, while the strip, calendar and help still do
- [ ] A note always opens in NORMAL, even when empty
- [ ] The cursor is clamped to the last character in NORMAL
- [ ] `escape` from INSERT goes to NORMAL, and from plain NORMAL closes the note
- [ ] A new `vim` test marker exists, and new test files are registered in the feature table
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for the adapter
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
