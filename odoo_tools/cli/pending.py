# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from ..utils import pending_merge as pm_utils


@click.group()
def cli():
    pass


@cli.command(name="show")
@click.argument("repo_path")
def show_pending(repo_path):
    repo = pm_utils.Repo(repo_path)
    repo.show_prs()


if __name__ == "__main__":
    cli()
