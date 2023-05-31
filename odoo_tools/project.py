# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from .utils.misc import copy_file, get_template_path

DC_EX_FILENAME = "example.docker-compose.override.yml"
DC_EX_FILE_PATH = get_template_path(DC_EX_FILENAME)


def create_doco_override():
    # TODO: pass destination path
    # or simply guess the root path
    copy_file(DC_EX_FILE_PATH, "./docker-compose.override.yml")


@click.group()
def cli():
    pass


@cli.command()
def init():
    click.echo("Preparing project...")
    create_doco_override()


if __name__ == '__main__':
    cli()
