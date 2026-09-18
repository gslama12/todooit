# Development

## Layout

| Path | What is in it |
| --- | --- |
| `todooit/` | The app: a Textual TUI, todos in a tree of projects, SQLite via SQLAlchemy |
| `todooit/api/` | The models and the operations on them |
| `todooit/ui/` | Screens, trees, renderers and the config API |
| `todooit/extras/` | Formatter and status-bar widget library, merged in from dooit-extras |
| `todooit/utils/default_config.py` | The configuration: keybinds, formatters, bar, dashboard, colors |
| `tests/` | The test suite |
| `site/` | This documentation site |

Most appearance and behaviour changes belong in `default_config.py`.
Structural and rendering changes belong in the package —
`todooit/ui/widgets/renderers/`, `todooit/ui/api/`.

## Tests

```bash
uv sync
uv run pytest -q
```

Every test carries a marker for its feature, so a change can run only what it
touches:

```bash
uv run pytest -m smoke -n 4        # the sanity subset
uv run pytest -m notes             # one feature
uv run pytest -m "notes and ui"    # just its UI half
uv run pytest -m "move or sort"    # two features
uv run pytest -n auto              # everything
```

The markers are declared in `pyproject.toml` and applied by filename.
`--strict-markers` is on, so a typo in `-m` is an error rather than a run that
quietly selects nothing.

Tests never touch your database: the root `conftest.py` points `TODOOIT_HOME`
at a per-process directory under the temp directory before todooit is
imported.

CI runs the suite on every push to `main` and `dev`
(`.github/workflows/tests.yml`).

## Docs

The site is [VitePress](https://vitepress.dev/) in `site/`.

```bash
cd site
npm install
npm run docs:dev      # local preview
npm run docs:build    # what CI builds
```

It deploys to GitHub Pages on every push to `main`
(`.github/workflows/docs.yml`).

### Screenshots

The SVGs in `site/docs/public/screenshots/` are generated — do not edit them
by hand. The script drives the real app through Textual's pilot, headlessly,
against a throwaway database:

```bash
uv run --with "fonttools[woff]" python site/scripts/screenshots.py
```

It needs **JetBrainsMono Nerd Font Mono** installed. The font is subsetted to
the glyphs the frames actually draw and base64'd into each SVG, because Rich's
own template points at Fira Code on a CDN — which an `<img>` may not fetch, and
which has no Nerd Font glyphs anyway. Pass `--font-dir <path>` if the script
cannot find it.

Add a shot by adding a name, the project to stand in and the keys that get
there to `SCENES`. Write a chord one key at a time — `("g", "u")`, never
`("gu")` — since the pilot presses a key and there is no key called `gu`.

`COLUMNS` and `ROWS` set the frame. They are sized so the image comes out
square; changing one means changing the other to keep it that way.

::: warning Notes have to be typed
A note's markup is drawn as it is *typed*, so a note written straight into the
database renders as raw characters. `NOTE_KEYS` and `PINNED_KEYS` are typed
through the pilot for that reason.
:::
