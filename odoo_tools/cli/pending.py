# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

import arrow
import click
from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ..utils import gh, ui
from ..utils import pending_merge as pm_utils
from ..utils.click import (
    DEFAULT_MAX_WORKERS,
    deprecated_option,
    global_command_decorators,
    jobs_option,
)

console = Console()

PR_STATE_STYLES = {"open": "green", "closed": "red", "merged": "magenta"}


@click.group()
@global_command_decorators
def cli():
    pass


def _resolve_repos(repo_paths):
    """Return the repos with a pending-merges file, among ``repo_paths`` if given.

    Each given repo can be designated either by its path or by its name.
    """
    pending_repos = pm_utils.Repo.repositories_from_pending_folder(path_check=False)
    if not repo_paths:
        return pending_repos
    pending_repos_by_path = {repo.path: repo for repo in pending_repos}
    repos = {}
    for repo_path in repo_paths:
        # Accept both a bare repo name and a submodule path
        path = pm_utils.Repo(repo_path, path_check=False).path
        if path not in pending_repos_by_path:
            ui.err_console.print(
                f"Warning: {repo_path} has no pending merges, skipping.",
                style="yellow",
            )
            continue
        repos[path] = pending_repos_by_path[path]
    return list(repos.values())


@cli.command(name="show")
@click.argument(
    "repo_paths",
    required=False,
    nargs=-1,
)
@click.option(
    "--check/--no-check",
    "check",
    is_flag=True,
    default=True,
    help="Check each pull request's state via the GitHub API",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output as JSON",
)
@jobs_option
@deprecated_option(
    "--purge",
    message="`--purge` has been removed from `otools-pending show`. "
    "Use `otools-pending clean` instead.",
)
def show_pending(repo_paths=(), check=True, as_json=False, jobs=DEFAULT_MAX_WORKERS):
    """List pull requests on <repo_path>."""
    repos = _resolve_repos(repo_paths)
    all_prs = [pr for repo in repos for pr in repo._iter_pending_pull_requests()]
    if check:
        ui.warn_missing_github_token()
    # ids of PRs whose enrichment failed -> error message
    errors: dict[int, str] = {}
    # Shared by every row: a new one per rebuild would restart the animation
    spinner = Spinner("dots")
    # In case of --json, output directly
    if as_json:
        if check:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                futures = {pool.submit(pr.enrich_with_github): pr for pr in all_prs}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        # leave state as None in the JSON output
                        pass
        click.echo(json.dumps([pr.to_dict() for pr in all_prs], indent=2, default=str))
        return

    def build_grid():
        grid = Table.grid(padding=(0, 1))
        grid.add_column(no_wrap=True)  # state dot / spinner
        grid.add_column(no_wrap=True)  # shortcut (linked)
        grid.add_column(no_wrap=True, style="dim")  # patch marker
        grid.add_column()  # title
        grid.add_column(no_wrap=True, justify="right", style="dim")  # last updated
        for pr in all_prs:
            if not check:
                state_cell, updated, title = "-", "", ""
            elif id(pr) in errors:
                state_cell, updated = "[red]?[/]", ""
                title = Text(
                    errors[id(pr)], style="red", no_wrap=True, overflow="ellipsis"
                )
            elif not pr.is_enriched:
                state_cell, updated, title = spinner, "", ""
            else:
                state = "merged" if pr.merged else pr.state
                state_cell = f"[{PR_STATE_STYLES.get(state, 'white')}]●[/]"
                updated = arrow.get(pr.updated_at).humanize() if pr.updated_at else ""
                title = Text(pr.title or "", no_wrap=True, overflow="ellipsis")
            grid.add_row(
                state_cell,
                f"[link={pr.url}]{pr.shortcut}[/link]",
                "(patch)" if pr.is_patch else "",
                title,
                updated,
            )
        return grid

    if check and all_prs:
        with (
            Live(build_grid(), console=console, refresh_per_second=10) as live,
            ThreadPoolExecutor(max_workers=jobs) as pool,
        ):
            futures = {pool.submit(pr.enrich_with_github): pr for pr in all_prs}
            for future in as_completed(futures):
                pr = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    errors[id(pr)] = str(exc)
                live.update(build_grid())
    else:
        console.print(build_grid())


def _aggregate_repos(repos, push=True, target_branch=None, jobs=DEFAULT_MAX_WORKERS):
    """Aggregate (and push) the given repos in parallel.

    Aggregating is mostly waiting on the network, so several submodules are
    handled at once. Their output can't be printed as it comes -- it would be
    interleaved, and would fight with the progress display -- so each repo
    logs to its own file, and the last line of it is shown as its progress.
    Those logs are thrown away unless the repo failed, or we are in debug mode.

    :raises Exit: if any of the repos failed, after reporting them all.
    """
    if not repos:
        return
    # Resolve the target branch once for all of them: it is the same for every
    # repo, and asking for it may prompt, which can't happen once the parallel
    # aggregation (and the live display it draws) has started.
    if push and not target_branch:
        target_branch = gh.get_target_branch()

    def make_task(repo):
        def task(progress):
            progress.set_status("aggregating")
            repo.run_aggregate()
            if push:
                progress.set_status("pushing")
                repo.push_to_remote(target_branch=target_branch)

        return task

    # Keyed by name, which is also what's worth reading on the display: a name
    # determines a submodule path, and _resolve_repos() returns each path once.
    tasks = {repo.name: make_task(repo) for repo in repos}
    ui.run_tasks(
        tasks,
        max_workers=jobs,
        console=console,
        title="Aggregating submodules",
        exit_on_failure=True,
    )


@cli.command(name="clean")
@click.argument(
    "repo_paths",
    required=False,
    nargs=-1,
)
@click.option(
    "--aggregate/--no-aggregate",
    "aggregate",
    is_flag=True,
    default=None,
    help="Run git aggregate (and push) on each touched repo after purging. "
    "If not set, you will be prompted once.",
)
@jobs_option
def clean_pending(repo_paths=(), aggregate=None, jobs=DEFAULT_MAX_WORKERS):
    """Remove merged pull requests from pending-merge files."""
    to_aggregate = purge_repos(_resolve_repos(repo_paths), jobs=jobs)
    if not to_aggregate:
        return
    # Re-aggregating performs an upgrade of the submodules, potentially pulling
    # breaking changes from the remaining pending merges, so unless the choice
    # was made explicit via the flag, ask first -- once for all of them.
    if aggregate is None:
        names = ", ".join(repo.name for repo in to_aggregate)
        aggregate = Confirm.ask(
            f"Re-aggregate {names}? This may pull new changes "
            "from the remaining pending merges",
            default=True,
        )
    if not aggregate:
        return
    _aggregate_repos(to_aggregate, jobs=jobs)


def _cleaned_summary(removed: int, total: int, unreachable: int) -> str:
    """What the purge came to.

    A pull request nobody could get a verdict on is worth saying: it stays
    pending, and the count of what was cleaned alone would read as a clean run.
    """
    cleaned = f"Cleaned {removed} pending merge(s)"
    if unreachable:
        return f"{cleaned}; {unreachable} of {total} could not be checked"
    if not removed:
        return f"No merged pull request among the {total} pending"
    return cleaned


def _purge_task(pull_request, progress):
    """Ask GitHub about one pending pull request, and drop it if it is merged."""
    progress.set_status("checking")
    pull_request.enrich_with_github()
    if not pull_request.merged:
        # Worth recording, not worth a row: most pull requests are still open,
        # and a screen full of them buries the few that were dropped.
        progress.set_outcome("kept", hide=True)
        return
    pull_request.remove_from_merges_file()
    progress.set_outcome("removed", icon=Text("●", style=PR_STATE_STYLES["merged"]))


def purge_repos(repos, jobs=DEFAULT_MAX_WORKERS):
    """Drop the merged pull requests from the given repos' pending merges.

    Every pull request of every repo is asked about at once -- one request
    each, and there are dozens of them -- and each shows its verdict on its own
    row as it arrives. A merged one is dropped from its merges file there and
    then, which is safe from a worker: see the lock in
    :mod:`~odoo_tools.utils.pending_merge`.

    One that GitHub could not be reached about is reported and left alone: with
    no verdict, the safe answer is that it is still pending.

    A repo left without any pending merge at all has its merges file disposed
    of, which is the end of it. The others are the answer.

    :param repos: repos that have a pending-merges file; see `_resolve_repos`.
    :returns: the repos that still have pending merges, so are worth
        re-aggregating.
    """
    all_prs = [pr for repo in repos for pr in repo._iter_pending_pull_requests()]
    if not all_prs:
        return []
    ui.warn_missing_github_token()
    results = ui.run_tasks(
        {pr.shortcut: partial(_purge_task, pr) for pr in all_prs},
        max_workers=jobs,
        console=console,
        title="Cleaning pending merges",
    )
    answered = {result.label for result in results if result.ok}
    removed = [pr for pr in all_prs if pr.merged and pr.shortcut in answered]
    console.print(
        _cleaned_summary(len(removed), len(all_prs), len(all_prs) - len(answered)),
        highlight=False,
    )
    # Dispose of the merges files left without any pending merge, and keep the
    # rest for re-aggregation.
    to_aggregate = []
    for repo in sorted({pr._repo for pr in removed}, key=lambda repo: repo.name):
        if repo.has_any_pr_left():
            to_aggregate.append(repo)
        else:
            repo._handle_empty_merges_file()
    return to_aggregate


@cli.command(name="aggregate")
@click.argument("repo_paths", nargs=-1, required=True)
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
@jobs_option
def aggregate(repo_paths, target_branch=None, push=None, jobs=DEFAULT_MAX_WORKERS):
    """Perform a git aggregation on each <repo_path>."""
    repos = _resolve_repos(repo_paths)
    _aggregate_repos(repos, push=push, target_branch=target_branch, jobs=jobs)


@cli.command(name="add")
@click.argument("entity_urls", nargs=-1, required=True)
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
@click.option(
    "--push/--no-push",
    "push",
    is_flag=True,
    default=True,
    help="push the result of the aggregation to a remote branch",
)
@jobs_option
def add_pending(
    entity_urls,
    aggregate=True,
    patch=False,
    push=True,
    jobs=DEFAULT_MAX_WORKERS,
):
    """Add one or more pending merges using the given entity link(s)"""
    # pattern, given an https://github.com/<user>/<repo>/pull/<pr-index>
    # # PR headline
    # # PR link as is
    # - refs/pull/<pr-index>/head
    # Add every pending merge to its file first, without aggregating, and
    # collect the affected repos deduplicated by their merges file so that a
    # submodule referenced by several URLs is aggregated only once.
    repos = {}
    for entity_url in entity_urls:
        repo = pm_utils.add_pending(entity_url, aggregate=False, patch=patch)
        repos[repo.abs_merges_path] = repo
    # Then aggregate each affected submodule once.
    if aggregate:
        _aggregate_repos(list(repos.values()), push=push, jobs=jobs)


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
