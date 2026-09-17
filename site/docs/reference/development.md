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
uv run python site/scripts/screenshots.py
```

Add a shot by adding a name and the keys that get to it to `SCENES` in that
script.
