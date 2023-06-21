# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from .utils.misc import copy_file, get_template_path

DC_EX_FILENAME = "example.docker-compose.override.yml"
BUMPVERSION_EX_FILENAME = "example.bumpversion.cfg"

INIT_FILE_TEMPLATES = (
    {
        "source": DC_EX_FILENAME,
        "destination": "./docker-compose.override.yml",
    },
    {
        "source": BUMPVERSION_EX_FILENAME,
        "destination": "./.bumpversion.cfg",
    },
)


def bootstrap_files():
    # TODO: pass destination path
    # or simply guess the root path
    for item in INIT_FILE_TEMPLATES:
        copy_file(get_template_path(item["source"]), item["destination"])


@click.group()
def cli():
    pass


@cli.command()
def init():
    click.echo("Preparing project...")
    bootstrap_files()


if __name__ == '__main__':
    cli()
