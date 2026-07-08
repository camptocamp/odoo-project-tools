# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import arrow
import click
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.spinner import Spinner
from rich.table import Table

from ..utils import pending_merge as pm_utils
from ..utils import ui
from ..utils.click import deprecated_option, global_command_decorators

console = Console()

PR_STATE_STYLES = {"open": "green", "closed": "red", "merged": "magenta"}


@click.group()
@global_command_decorators
def cli():
    pass


def _resolve_repos(repo_paths, path_check=True):
    if not repo_paths:
        return pm_utils.Repo.repositories_from_pending_folder(path_check=path_check)
    return [pm_utils.Repo(repo_path, path_check=path_check) for repo_path in repo_paths]


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
@deprecated_option(
    "--purge",
    message="`--purge` has been removed from `otools-pending show`. "
    "Use `otools-pending clean` instead.",
)
def show_pending(repo_paths=(), check=True, as_json=False):
    """List pull requests on <repo_path>."""
    repos = _resolve_repos(repo_paths, path_check=False)
    all_prs = [pr for repo in repos for pr in repo._iter_pending_pull_requests()]
    if check:
        ui.warn_missing_github_token()
    # ids of PRs whose enrichment failed -> error message
    errors: dict[int, str] = {}
    # In case of --json, output directly
    if as_json:
        if check:
            with ThreadPoolExecutor(max_workers=8) as pool:
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
        grid.add_column(no_wrap=True, overflow="ellipsis")  # title
        grid.add_column(no_wrap=True, justify="right", style="dim")  # last updated
        for pr in all_prs:
            if not check:
                state_cell, updated, title = "-", "", ""
            elif id(pr) in errors:
                state_cell = "[red]?[/]"
                updated = ""
                title = f"[red]{escape(errors[id(pr)])}[/]"
            elif not pr.is_enriched:
                state_cell, updated, title = Spinner("dots"), "", ""
            else:
                state = "merged" if pr.merged else pr.state
                state_cell = f"[{PR_STATE_STYLES.get(state, 'white')}]●[/]"
                updated = arrow.get(pr.updated_at).humanize() if pr.updated_at else ""
                title = pr.title or ""
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
            ThreadPoolExecutor(max_workers=8) as pool,
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
    default=True,
    help="Run git aggregate (and push) on each touched repo after purging",
)
def clean_pending(repo_paths=(), aggregate=True):
    """Remove merged pull requests from pending-merge files."""
    repos = _resolve_repos(repo_paths)
    all_prs = [pr for repo in repos for pr in repo._iter_pending_pull_requests()]
    if not all_prs:
        return
    ui.warn_missing_github_token()
    touched_repos: set[pm_utils.Repo] = set()
    removed: set[int] = set()  # ids of PRs removed from their merges file
    # ids of PRs whose enrichment failed -> error message
    errors: dict[int, str] = {}

    def build_grid():
        grid = Table.grid(padding=(0, 1))
        grid.add_column(no_wrap=True)  # state dot / spinner
        grid.add_column(no_wrap=True)  # shortcut (linked)
        grid.add_column(no_wrap=True, style="dim")  # patch marker
        grid.add_column(no_wrap=True, overflow="ellipsis")  # outcome
        for pr in all_prs:
            if id(pr) in errors:
                state_cell = "[red]?[/]"
                outcome = f"[red]{escape(errors[id(pr)])}[/]"
            elif not pr.is_enriched:
                state_cell, outcome = Spinner("dots"), ""
            elif id(pr) in removed:
                state = "merged" if pr.merged else pr.state
                state_cell = f"[{PR_STATE_STYLES.get(state, 'white')}]●[/]"
                outcome = "[green]removed[/]"
            else:
                continue  # enriched but not removed — nothing to do here
            grid.add_row(
                state_cell,
                f"[link={pr.url}]{pr.shortcut}[/link]",
                "(patch)" if pr.is_patch else "",
                outcome,
            )
        return grid

    # Enrich every PR via the GitHub API in parallel; remove the merged ones
    # from the merges file as soon as we know the verdict, on the main thread
    # (so concurrent yaml edits stay race-free).
    with (
        Live(build_grid(), console=console, refresh_per_second=10) as live,
        ThreadPoolExecutor(max_workers=8) as pool,
    ):
        futures = {pool.submit(pr.enrich_with_github): pr for pr in all_prs}
        for future in as_completed(futures):
            pr = futures[future]
            try:
                future.result()
            except Exception as exc:
                # Leave the PR in place; we can't tell if it was merged.
                errors[id(pr)] = str(exc)
                live.update(build_grid())
                continue
            if pr.merged:
                if pr.is_patch:
                    pr._repo.remove_pending_pull_from_patches(pr.owner, pr.pr)
                else:
                    pr._repo.remove_pending_pull(pr.owner, pr.pr)
                touched_repos.add(pr._repo)
                removed.add(id(pr))
            live.update(build_grid())
    # Per-repo post-processing: clean up an empty merges file or re-aggregate.
    for repo in touched_repos:
        if not repo.has_any_pr_left():
            repo._handle_empty_merges_file(delete_file=True)
        elif aggregate:
            repo.run_aggregate()
            repo.push_to_remote()


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
    repo.run_aggregate()
    if push:
        repo.push_to_remote(target_branch=target_branch)


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
def add_pending(entity_urls, aggregate=True, patch=False, push=True):
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
        for repo in repos.values():
            repo.run_aggregate()
            if push:
                repo.push_to_remote()


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
