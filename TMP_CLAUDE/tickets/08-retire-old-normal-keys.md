# 08: Retire old NORMAL keys

**What to build:** The old note keys give way to the spec, the features they served stay reachable, and the hint line tells the truth.

**Blocked by:** 06, 07

**Status:** ready-for-agent

- [ ] `gx` opens the link under the cursor, or reports that there is none
- [ ] `gf` hands the keyboard to the attachment strip, whose own keys are unchanged
- [ ] Bare `u`, `d`, `f`, `o`, `0` and `$` no longer do their old jobs
- [ ] `ctrl+u` and `ctrl+d`, and their Cmd equivalents on Mac, are half page in NORMAL
- [ ] In INSERT, `ctrl+u` clears the line and `ctrl+d` clears the note after its y/N prompt
- [ ] `ctrl+c`, `ctrl+x`, `ctrl+v`, `ctrl+a` and shift-selection keep working
- [ ] The hint line is built from the configured keys
- [ ] Existing tests pressing old keys, including the Karabiner and keyboard-layout tests, are updated
- [ ] Note-window pilot tests cover this behaviour
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
