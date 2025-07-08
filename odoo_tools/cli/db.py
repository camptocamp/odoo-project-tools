# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import datetime
from pathlib import Path

import click
import psycopg2
from rich.console import Console
from rich.table import Table

from .. import utils

console = Console()


@click.group()
@click.option("--debug", is_flag=True)
def cli(**kwargs):
    """Database management commands."""
    pass


@cli.command()
@utils.click.handle_exceptions()
def list():
    """List all databases in the container."""
    db_list = utils.db.get_db_list()
    if not db_list:
        click.echo("No databases found")
        return
    # Report a nice table
    table = Table("Name")
    for db_name in sorted(db_list):
        table.add_row(db_name)
    console.print(table)


@cli.command("list-versions")
@utils.click.handle_exceptions()
def list_versions():
    """Print a table of DBs with Marabunta version and install date."""
    res = {}
    for db_name in utils.db.get_db_list():
        try:
            version_fetch = utils.db.execute_db_request(
                db_name,
                """
                SELECT date_done, number
                FROM marabunta_version
                ORDER BY date_done DESC
                LIMIT 1;
                """,
            )
            version_tuple = version_fetch[0] if version_fetch else (None, None)
        except psycopg2.ProgrammingError:
            # Error expected when marabunta_version table does not exist
            version_tuple = (None, None)
        res[db_name] = version_tuple
    # Early return if no databases found
    if not res:
        click.echo("No databases found")
        return
    # Report a nice table
    table = Table("Database", "Version", "Install Date")
    for db_name, (install_date, version) in sorted(
        res.items(), key=lambda x: x[1][0] or datetime.min, reverse=True
    ):
        install_date = install_date.strftime("%Y-%m-%d") if install_date else None
        table.add_row(db_name, version, install_date)
    console.print(table)


@cli.command()
@click.argument("dump_path", type=click.Path(exists=True, readable=True))
@click.option(
    "--db-name",
    help="Name of the database to restore to. If not specified, uses the dump filename.",
)
@click.option(
    "--create-template/--no-create-template",
    help="Create a template database for faster restores in the future.",
)
@utils.click.handle_exceptions()
def restore(dump_path, db_name=None, create_template=False):
    """Restore a PostgreSQL dump to a database."""
    # Use filename without extension as db name by default
    if not db_name:
        db_name = Path(dump_path).stem
    # Create database
    template_db_name = create_template and f"{db_name}-template" or None
    utils.db.create_db_from_db_dump(db_name, dump_path, template_db_name)


@cli.command()
@click.argument("db_name", default="odoodb")
@click.argument("output_path", default=".", type=click.Path(exists=False))
@click.option(
    "--format",
    type=click.Choice(["c", "p"]),
    default="c",
    help="Format of the dump (c: custom, p: plain)",
)
@utils.click.handle_exceptions()
def dump(db_name, output_path, format):
    """Create a PostgreSQL dump of the specified database.

    DB_NAME: Name of the database to dump.
    Defaults to "odoodb".

    OUTPUT_PATH: Path of the file or directory to save the dump.
    If it's a directory, the filename will be automatically generated.
    Defaults to the current directory.
    """
    utils.db.dump_db(db_name, output_path, format)


if __name__ == "__main__":
    cli()
