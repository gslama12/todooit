# Installation

todooit needs Python 3.9 or newer and runs on macOS, Linux and WSL.

::: tip Terminal
todooit was only tested on WezTerm. Other terminals may not show every icon
correctly. The icons are Nerd Font glyphs, so use a patched font.
<!-- TODO: verify -->
:::

## From source

Each of these installs the app editable, so editing the source edits the
running app.

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

## Try it without touching your todos

```bash
todooit --dev
```

That runs against `~/.local/share/todooit-dev` — its own database, cache and
config. See [Data & files](/reference/data).
