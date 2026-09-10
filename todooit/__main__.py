import os
from pathlib import Path
from typing import Optional

import click

from todooit.paths import DEV_HOME, HOME_ENV_VAR, config_file

VERSION = "1.0.0"


def run_dooit(config: Optional[str] = None, db_path: Optional[str] = None):
    config_path = None if not config else Path(config)

    if config_path and not (config_path.exists() and config_path.is_file()):
        print(f"Config file {config} not found.")
        return

    from todooit.ui.tui import Dooit

    Dooit(config=config_path, db_path=db_path).run()


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.option(
    "--version",
    "-v",
    is_flag=True,
    help="Show version and exit.",
)
@click.option("-c", "--config", default=None, help="Path to config file")
@click.option("--db", default=None, help="Path to database file")
@click.option(
    "--dev",
    is_flag=True,
    help="Run an isolated dev instance (own database, cache and config).",
)
@click.pass_context
def main(ctx, version: bool, config: str, db: str, dev: bool) -> None:
    if version:
        return print(f"todooit - {VERSION}")

    # Must happen before anything imports the package: Dooit.CSS_PATH is
    # evaluated in the class body, so the cache dir is resolved at import time.
    # setdefault so an explicit TODOOIT_HOME still wins over --dev.
    if dev:
        os.environ.setdefault(HOME_ENV_VAR, str(DEV_HOME))

    if ctx.invoked_subcommand is None:
        run_dooit(config=config, db_path=db)


@main.command(help="Show config location.")
def config_loc() -> None:
    """Print the location of the configuration file."""
    print(config_file())


if __name__ == "__main__":
    main()
