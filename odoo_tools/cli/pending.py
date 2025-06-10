# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from ..utils import pending_merge as pm_utils
from ..utils import ui


@click.group()
def cli():
    pass


@cli.command(name="show")
@click.argument(
    "repo_paths",
    required=False,
    nargs=-1,
)
@click.option(
    "-s",
    "--state",
    "state",
    help="only list pull requests in the specified state",
    type=click.Choice(["open", "merged", "closed"], case_sensitive=False),
)
@click.option(
    "-p",
    "--purge",
    "purge",
    help="remove the pull request in a state matching the value if the option from the git-aggregator file",
    type=click.Choice(["closed", "merged"], case_sensitive=False),
)
@click.option(
    "--yes-all/--no-all",
    "yes_all",
    is_flag=True,
    default=True,
    help="assume yes to all questions, useful for automation",
)
def show_pending(repo_paths=(), state=None, purge=None, yes_all=True):
    """List pull requests on <repo_path>"""
    if yes_all:
        ui.echo("``--yes-all`` flag on -> Assuming yes to all questions")
    if not repo_paths:
        repositories = pm_utils.Repo.repositories_from_pending_folder()
    else:
        repositories = [pm_utils.Repo(repo_path) for repo_path in repo_paths]
    for repo in repositories:
        repo.show_prs(state=state, purge=purge, yes_all=yes_all)


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
    default=True,
    help="push the result of the aggregation to a remote branch",
)
def aggregate(repo_path, target_branch=None, push=None):
    """Perform a git aggregation on <repo_path>."""
    repo = pm_utils.Repo(repo_path)
    aggregator = repo.get_aggregator(target_branch=target_branch)
    aggregator.aggregate()
    if push:
        aggregator.push()


@cli.command(name="add")
@click.argument("entity_url")
@click.option(
    "--aggregate/--no-aggregate",
    "aggregate",
    help="run git aggregate. This is the default behavior.",
    is_flag=True,
    default=True,
)
@click.option(
    "--patch",
    "patch",
    help="Add a patch to the pending merge file instead of a PR. "
    "Very handy to avoid conflicts or to prevent additional commits to be added to the repo.",
    is_flag=True,
    default=False,
)
def add_pending(entity_url, aggregate=True, patch=False):
    """Add a pending merge using given entity link"""
    # pattern, given an https://github.com/<user>/<repo>/pull/<pr-index>
    # # PR headline
    # # PR link as is
    # - refs/pull/<pr-index>/head
    pm_utils.add_pending(entity_url, aggregate=aggregate, patch=patch)


@cli.command(name="remove")
@click.argument("entity_url")
@click.option(
    "--aggregate/--no-aggregate",
    "aggregate",
    help="run git aggregate. This is the default behavior.",
    is_flag=True,
    default=True,
)
def remove_pending(entity_url, aggregate=True):
    """Add a pending merge using given entity link"""
    # pattern, given an https://github.com/<user>/<repo>/pull/<pr-index>
    # # PR headline
    # # PR link as is
    # - refs/pull/<pr-index>/head
    pm_utils.remove_pending(entity_url, aggregate=aggregate)


if __name__ == "__main__":
    cli()
