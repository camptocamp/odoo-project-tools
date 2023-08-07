# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from ..utils import pending_merge as pm_utils


@click.group()
def cli():
    pass


@cli.command(name="show")
@click.argument("repo_path")
@click.option("-s", "--state", "state")
@click.option(
    "-p",
    "--purge",
    "purge",
    type=click.Choice(['closed', 'merged'], case_sensitive=False),
)
def show_pending(repo_path, state=None, purge=None):
    repo = pm_utils.Repo(repo_path)
    repo.show_prs(state=state, purge=purge)


if __name__ == "__main__":
    cli()
