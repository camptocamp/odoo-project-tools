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


# TODO: add tests
@cli.command(name="aggregate")
@click.argument("repo_path")
@click.option("-t", "--target-branch", "target_branch")
@click.option("--push/--no-push", "push", is_flag=True, default=False)
def aggregate(repo_path, target_branch=None, push=None):
    repo = pm_utils.Repo(repo_path)
    aggregator = repo.get_aggregator(target_branch=target_branch)
    aggregator.aggregate()
    if push:
        aggregator.push()


if __name__ == "__main__":
    cli()
