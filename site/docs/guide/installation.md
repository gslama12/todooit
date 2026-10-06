# Installation

todooit needs Python 3.9 or newer and runs on macOS, Linux and WSL.

```bash
uv tool install todooit
todooit
```

That puts `todooit` on your `PATH` in an environment of its own. To work on
todooit itself, install it [from source](#from-source) instead.

::: tip Terminal and font
todooit was only tested on [WezTerm](https://wezterm.org/). Other terminals may
not show every icon correctly.

The icons are Nerd Font glyphs, so the terminal needs a patched font.
[JetBrainsMono Nerd Font](https://www.nerdfonts.com/font-downloads) is what the
screenshots on this site are rendered in:

```lua
-- ~/.config/wezterm/wezterm.lua
config.font = wezterm.font('JetBrainsMono Nerd Font')
config.font_size = 10.5
config.color_scheme = 'Tokyo Night'
```

Leave `enable_kitty_keyboard` off. With it on, WezTerm also reports the text of
a `ctrl+<letter>` chord, and the note editor reads that as a printable
character — so `ctrl+e` types an `e` instead of running the binding.
:::

## Cmd shortcuts on macOS

On a Mac every `ctrl` binding also answers to `cmd`: `cmd+c` copies, `cmd+v`
pastes, `cmd+z` takes back, `cmd+q` quits, and so on. The terminal has to pass
those keys on first, and WezTerm doesn't by default. It keeps `cmd+c`, `cmd+v`,
`cmd+n` and `cmd+q` for itself (copy, paste, new window, quit), and it sends any
other `cmd` chord as the bare letter, since `enable_kitty_keyboard` stays off.

The fix is to have WezTerm send each chord as a `cmd` key, but only while
todooit is the program in front, so every other program keeps WezTerm's usual
behavior:

```lua
-- ~/.config/wezterm/wezterm.lua
local act = wezterm.action

-- todooit runs as `python`, so look for it on the command line, not in the
-- process name.
local function is_todooit(pane)
  local info = pane:get_foreground_process_info()
  if not info then return false end
  for _, arg in ipairs(info.argv or {}) do
    if arg:match 'todooit' then return true end
  end
  return false
end

-- In todooit, send the chord as cmd+<key>; anywhere else, do `fallback`
-- (or nothing, if there is none).
local function cmd_key(char, fallback)
  local seq = string.format('\x1b[%d;9u', string.byte(char))
  return wezterm.action_callback(function(window, pane)
    if is_todooit(pane) then
      pane:send_text(seq)
    elseif fallback then
      window:perform_action(fallback, pane)
    end
  end)
end

config.keys = {
  { key = 'c', mods = 'CMD', action = cmd_key('c', act.CopyTo 'Clipboard') },
  { key = 'v', mods = 'CMD', action = cmd_key('v', act.PasteFrom 'Clipboard') },
  { key = 'x', mods = 'CMD', action = cmd_key 'x' },
  { key = 'a', mods = 'CMD', action = cmd_key 'a' },
  { key = 'z', mods = 'CMD', action = cmd_key 'z' },
  { key = 'y', mods = 'CMD', action = cmd_key 'y' },
  { key = 'd', mods = 'CMD', action = cmd_key 'd' },
  { key = 'n', mods = 'CMD', action = cmd_key('n', act.SpawnWindow) },
  { key = 'q', mods = 'CMD', action = cmd_key('q', act.QuitApplication) },
}
```

If your config already binds any of these keys, add the `is_todooit` check to
your existing binding rather than defining the key a second time.

`\x1b[<code>;9u` is how the kitty keyboard encoding spells `cmd+<key>`.
todooit reads that sequence whether or not `enable_kitty_keyboard` is on, so
the tip above still holds. In todooit, `cmd+v` is a key press, not a terminal
paste, because todooit reads the clipboard itself. That's what lets it paste a
task as a new row and attach a copied file in a note. With a mouse selection,
`cmd+c` still copies inside todooit: it copies the task's description, not the
selected text.

If your config sends `cmd+left` / `cmd+right` as `^A` / `^E` (start / end of
line at a shell prompt), send Home / End to todooit instead: in todooit `^A`
is `ctrl+a`, the same key as `cmd+a`, so it selects all.

```lua
{ key = 'LeftArrow',  mods = 'CMD', action = wezterm.action_callback(function(window, pane)
    pane:send_text(is_todooit(pane) and '\x1b[H' or '\x01')
  end) },
{ key = 'RightArrow', mods = 'CMD', action = wezterm.action_callback(function(window, pane)
    pane:send_text(is_todooit(pane) and '\x1b[F' or '\x05')
  end) },
```

Likewise `cmd+up` / `cmd+down` (top / bottom of the document) only scroll
WezTerm's scrollback, which a full-screen program never sees. Send todooit
`ctrl+home` / `ctrl+end` (`'\x1b[1;5H'` / `'\x1b[1;5F'`) the same way, and
anywhere else fall back to `act.ScrollToTop` / `act.ScrollToBottom`.

The other terminal spellings of the Mac editing chords work as they are:
`opt+left/right` (`ESC b` / `ESC f`), `opt+backspace`, `opt+delete` (`ESC d`),
`shift+opt+left/right`, and `cmd+backspace` (`^U`, clears the line).

## From source

For development. Each of these installs the app editable, so editing the
source edits the running app.

::: code-group

```bash [uv]
git clone https://github.com/gslama12/todooit
cd todooit
uv venv .venv && source .venv/bin/activate
uv pip install -e .
todooit
```

```bash [venv]
git clone https://github.com/gslama12/todooit
cd todooit
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
todooit
```

```bash [conda]
git clone https://github.com/gslama12/todooit
cd todooit
conda create -n todooit python=3.12 && conda activate todooit
pip install -e .
todooit
```

:::

## Coming from dooit

`uv run python migration/db_migration.py` copies your dooit database into
todooit. Your dooit database is left as it is. See
[Migrating from dooit](/reference/data#migrating-from-dooit) for what carries
over.

## Try it without touching your todos

```bash
todooit --dev
```

That runs against `~/.local/share/todooit-dev` — its own database, cache and
config. See [Data & files](/reference/data).
