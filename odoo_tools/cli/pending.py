# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from ..utils import pending_merge as pm_utils


@click.group()
def cli():
    pass


@cli.command(name="show")
@click.argument("repo_path")
@click.option(
    "-s",
    "--state",
    "state",
    help="only list pull requests in the specified state (open, merged, closed)",
)  # TODO list valid values
@click.option(
    "-p",
    "--purge",
    "purge",
    help="remove the pull request in a state matching the value if the option from the git-aggregator file",
    type=click.Choice(['closed', 'merged'], case_sensitive=False),
)
def show_pending(repo_path, state=None, purge=None):
    """List pull requests on <repo_path>"""
    repo = pm_utils.Repo(repo_path)
    repo.show_prs(state=state, purge=purge)


# TODO: add tests
@cli.command(name="aggregate")
@click.argument("repo_path")
@click.option(
    "-t",
    "--target-branch",
    "target_branch",
    help="target branch where the aggregation should be pushed",
)
@click.option(
    "--push/--no-push",
    "push",
    is_flag=True,
    default=False,
    help="push the result of the aggregation to a remote branch",
)
def aggregate(repo_path, target_branch=None, push=None):
    """Perform a git aggregation on <repo_path>."""
    repo = pm_utils.Repo(repo_path)
    aggregator = repo.get_aggregator(target_branch=target_branch)
    aggregator.aggregate()
    if push:
        aggregator.push()


if __name__ == "__main__":
    cli()
