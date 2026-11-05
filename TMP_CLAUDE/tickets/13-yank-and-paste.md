# 13: Yank and paste

**What to build:** Text can be yanked and pasted through an internal register, working sensibly with the system clipboard.

**Blocked by:** 09

**Status:** ready-for-agent

- [ ] `y` works with motions, and `yy` yanks a line
- [ ] `p` and `P` paste after and before, respecting whether the yank was linewise, so `yyp` duplicates a line
- [ ] `d`, `c` and `x` also fill the register
- [ ] The register lasts for the app session, so a yank in one note pastes in another
- [ ] `y` also copies to the system clipboard, while `d`, `c` and `x` leave it alone
- [ ] `p` pastes the system clipboard through the existing paste path if it has changed since the last yank
- [ ] `p` always pastes text, and `ctrl+v` keeps attaching files
- [ ] Engine-seam tests cover this behaviour: keys in, then text, cursor, selection, mode and register out
- [ ] Note-window pilot tests cover this behaviour for the system clipboard
- [ ] Demo project seeded in this worktree's database, and the behaviour exercised in the running app
