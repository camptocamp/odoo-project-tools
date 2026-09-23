from functools import partial
from itertools import chain

import click
from rich.console import Console

from ..utils import gh, git, path, proj, ui
from ..utils import pending_merge as pm_utils
from ..utils.click import (
    DEFAULT_MAX_WORKERS,
    global_command_decorators,
    jobs_option,
)
from ..utils.config import config
from . import pending

console = Console()


@click.group()
@global_command_decorators
def cli():
    pass


def _run_submodule_tasks(tasks, jobs=DEFAULT_MAX_WORKERS, title=None):
    """Run one task per submodule, several submodules at a time.

    Submodule work is mostly waiting on the network -- populating the autoshare
    cache, fetching remotes, cloning -- so several are handled at once.

    Anything that may prompt, or that has to be decided or written once for the
    whole set, belongs before the call: there is no asking the user anything
    once the display is up, and no writing the superproject's own files from a
    worker (see :func:`~odoo_tools.utils.git.register_submodules`).

    :param tasks: the task to run, keyed by submodule path -- which is what
        identifies a submodule, what these commands take as an argument, and
        what is worth reading on the display.
    :param title: what this set of submodules is being put through, for a
        command that does more than one thing to them.
    :raises Exit: if any submodule failed, after reporting them all.
    """
    if not tasks:
        return
    # The caches the tasks read are filled here, on one thread, while the
    # terminal is still ours to print on.
    git.preload_submodule_state()
    ui.run_tasks(
        tasks,
        max_workers=jobs,
        console=console,
        title=title,
        exit_on_failure=True,
    )


def _init_task(submodule, progress):
    progress.set_status("updating" if submodule.exists else "adding")
    git.submodule_init(submodule)


@cli.command()
@jobs_option
@click.pass_context
def init(ctx, jobs=DEFAULT_MAX_WORKERS):
    """Add git submodules read in the .gitmodules files.

    Allows to edit the .gitmodules file, add all the repositories and
    run the command once to add all the submodules.

    It means less 'git submodule add -b ... {url} {path}' commands to run

    """
    submodules = list(git.iter_gitmodules())
    # The ones already checked out are updated, and updating expects them
    # registered. The others are added, which registers them on the way.
    git.register_submodules(
        submodule.path for submodule in submodules if submodule.exists
    )
    _run_submodule_tasks(
        {submodule.path: partial(_init_task, submodule) for submodule in submodules},
        jobs=jobs,
        title="Initializing submodules",
    )

    ui.echo("Submodules initialized.")
    ui.echo("")
    ui.echo("You can now update odoo/Dockerfile with this addons-path:")
    ui.echo("")
    ctx.invoke(ls, dockerfile=True)


@cli.command()
@click.option(
    "--dockerfile/--no-dockerfile",
    default=True,
    help="With --no-dockerfile, the raw paths are listed instead of the Dockerfile format",
)
def ls(dockerfile=False):
    """List git submodules paths.

    It can be used to directly copy-paste the addons paths in the Dockerfile.
    The order depends of the order in the .gitmodules file.
    """
    submodules = (submodule.path for submodule in git.iter_gitmodules())
    if dockerfile:
        odoo_src = config.odoo_src_rel_path
        local_src = config.local_src_rel_path
        external_src = config.ext_src_rel_path
        blacklist = {str(odoo_src)}
        # `.gitmodules` paths are already relative to the project root
        lines = (line for line in submodules if line not in blacklist)
        if config.template_version == 1:
            # odoo is checked out directly in `odoo_src_rel_path`
            base_addons_paths = [
                odoo_src / "odoo/addons",
                odoo_src / "addons",
            ]
        else:
            # v2 projects (deprecated) hold odoo and enterprise side by side
            base_addons_paths = [
                odoo_src / "odoo/odoo/addons",
                odoo_src / "odoo/addons",
                odoo_src / "enterprise",
            ]
        base_addons_paths.append(local_src)
        paid_modules_search = [
            local_src.parent / "paid-modules",
            external_src / "paid-modules",
            external_src / "3rd-party",
        ]
        trailing_addons_paths = [
            paid_modules
            for paid_modules in paid_modules_search
            if path.build_path(paid_modules).exists()
        ]
        lines = chain(
            base_addons_paths,
            lines,
            trailing_addons_paths,
        )
        lines = (f"/{line}" for line in lines)
        joined = ", \\\n".join(lines)
        click.echo(f'ENV ADDONS_PATH="{joined}" \\\n')
    else:
        for line in submodules:
            ui.echo(line)


@cli.command()
@click.argument("submodule_path", default="")
@click.option(
    "--force",
    is_flag=True,
    help="Force-update all submodules.",
)
@jobs_option
def update(submodule_path=None, force: bool = False, jobs=DEFAULT_MAX_WORKERS):
    """Initialize or update submodules

    Synchronize submodules and then launch `git submodule update --init`
    for each submodule. Several submodules are handled at a time; pass
    `--jobs 1` to get them one after the other.

    If `git-autoshare` is configured locally, it will add `--reference` to
    fetch data from local cache.

    By default, only submodules whose checked-out commit differs from the commit
    recorded by the current parent repository HEAD are updated, even when a specific
    submodule path is provided.
    To change this behavior, use the `--force` option.

    :param submodule_path: submodule path for a precise sync & update
    :param force: force-update submodules
    """
    submodules = list(git.iter_gitmodules(filter_path=submodule_path))
    if submodules and not force:
        # Asked once, here: `git submodule status` reports the whole
        # superproject, so there is nothing to gain from asking per submodule.
        out_of_sync = git.get_out_of_sync_submodules()
        submodules = [
            submodule for submodule in submodules if submodule.path in out_of_sync
        ]
    paths = [submodule.path for submodule in submodules]
    # Both write the superproject's own config, and both cost the same for
    # every submodule as for one, so they happen once here rather than N times
    # behind a lock.
    git.sync_submodules(paths)
    git.register_submodules(paths)
    _run_submodule_tasks(
        {submodule.path: partial(_update_task, submodule) for submodule in submodules},
        jobs=jobs,
        title="Updating submodules",
    )


def _update_task(submodule, progress):
    progress.set_status("updating")
    git.submodule_update(submodule.path, submodule=submodule)


@cli.command()
@click.argument("submodule_path", default="")
@click.option("--force-remote/--no-force-remote", default=False)
def sync_remote(submodule_path=None, repo=None, force_remote=False):
    """Use to alter remotes between camptocamp and upstream in .gitmodules.

    :param force_remote: explicit remote to add, if omitted, acts this way:

    * sets upstream to `camptocamp` if `merges` section of it's pending-merges
      file is populated

    * tries to guess upstream otherwise - for `odoo/src` path it is usually
      `OCA/OCB` repository, for anything else it would search for a fork in a
      `camptocamp` namespace and then set the upstream to fork's parent

    Mainly used as a post-execution step for add/remove-pending-merge but it's
    possible to call it directly from the command line.
    """

    assert submodule_path or repo
    repo = repo or pm_utils.Repo(submodule_path, path_check=False)

    new_remote_url = pm_utils.get_new_remote_url(repo=repo, force_remote=force_remote)

    git.set_remote_url(repo.path, new_remote_url)

    click.echo(f"Submodule {repo.path} is now being sourced from {new_remote_url}")

    if repo.has_pending_merges():
        # we're being polite here, excode 1 doesn't apply to this answer
        ui.ask_or_abort(f"Rebuild consolidation branch for {repo.name}?")
        push = ui.ask_confirmation(f"Push it to `{repo.company_git_remote}'?")
        repo.rebuild_consolidation_branch(push=push)

    else:
        odoo_version = proj.get_project_manifest_key("odoo_version")
        if ui.ask_confirmation(
            f"Submodule {repo.name} has no pending merges. Update it to {odoo_version}?"
        ):
            git.checkout(branch_name=odoo_version, cwd=repo.abs_path)


@cli.command()
@click.argument("submodule_path")
@click.option(
    "--target-branch",
    default=None,
    help="Target branch name. If omitted, computed automatically.",
)
def push(submodule_path, target_branch=None):
    """Push the current state of a submodule to the company remote."""
    repo = pm_utils.Repo(submodule_path)
    target_branch = target_branch or gh.get_target_branch()
    ui.echo(f"Pushing {repo.name} to {repo.company_git_remote}/{target_branch}")
    repo.push_to_remote(target_branch=target_branch)
    ui.echo("Done.")


@cli.command()
@click.argument("submodule_path", required=False, default=None)
@click.option(
    "--force-branch", default=None, help="Force checkout of a specific branch"
)
@click.option(
    "--clean-pending/--no-clean-pending",
    "clean_pending",
    is_flag=True,
    default=True,
    help="Purge merged PRs from the pending merges of the submodules that have"
    " some. This is the default behavior.",
)
@click.option(
    "--aggregate/--no-aggregate",
    "aggregate",
    is_flag=True,
    default=True,
    help="Rebuild the consolidation branch of the submodules that still have"
    " pending merges. This is the default behavior. With --no-aggregate, those"
    " submodules are skipped.",
)
@jobs_option
def upgrade(
    submodule_path, force_branch, clean_pending, aggregate, jobs=DEFAULT_MAX_WORKERS
):
    """Upgrade submodules to their latest remote commit.

    For submodules with pending merges, purge merged PRs first and
    re-aggregate if needed.

    Both behaviors can be disabled independently: with --no-clean-pending the
    pending merges are left as they are, and with --no-aggregate the submodules
    that still have pending merges are skipped instead of being re-aggregated.

    Several submodules are handled at a time; pass `--jobs 1` to get them one
    after the other.
    """
    ui.warn_missing_github_token()
    submodules = list(git.iter_gitmodules(filter_path=submodule_path))
    repos = {
        submodule.path: pm_utils.Repo(submodule.path, path_check=False)
        for submodule in submodules
    }
    if clean_pending:
        # Before deciding anything: purging can empty a submodule's pending
        # merges entirely, and that is what says whether it gets a rebuilt
        # consolidation branch or an upgrade to the latest remote commit.
        # Shared with `otools-pending clean`, down to the grid it draws.
        pending.purge_repos(
            [repo for repo in repos.values() if repo.has_pending_merges()], jobs=jobs
        )
        # A pull request GitHub could not be reached about stays pending, which
        # is the safe way round: the submodule keeps its consolidation branch
        # and gets rebuilt below rather than upgraded off it.
        # Read `.gitmodules` again: a submodule left with no pending merge has
        # its merges file disposed of, and that points its url back at the
        # upstream. What was read above says the company fork, which is where
        # the consolidation branch lived and has no version branch to upgrade
        # to.
        submodules = list(git.iter_gitmodules(filter_path=submodule_path))
    # A submodule with pending merges gets its consolidation branch rebuilt;
    # one without gets pulled up to its latest remote commit.
    rebuilding, upgrading = [], []
    for submodule in submodules:
        which = rebuilding if repos[submodule.path].has_pending_merges() else upgrading
        which.append(submodule)
    if not aggregate:
        for submodule in rebuilding:
            ui.echo(f"Skipping {submodule.path}: it has pending merges")
        rebuilding = []
    # Everything that may ask the user, asked now: there is no asking anything
    # once a step is running behind its display. The target branch is the same
    # for every submodule, so it is resolved once.
    odoo_version = proj.get_project_manifest_key("odoo_version")
    target_branch = gh.get_target_branch() if rebuilding else None
    upgrading = [
        submodule
        for submodule in upgrading
        if force_branch or _confirm_branch(submodule, odoo_version)
    ]

    # A consolidation branch that could not be rebuilt leaves the project in a
    # state nobody asked for, so the upgrades wait for a clean answer here
    # rather than piling more movement on top of it.
    _run_submodule_tasks(
        {
            submodule.path: partial(_rebuild_task, repos[submodule.path], target_branch)
            for submodule in rebuilding
        },
        jobs=jobs,
        title="Rebuilding consolidation branches",
    )
    # Only the ones being upgraded reach submodule_update, which expects them
    # registered; the ones getting their consolidation branch rebuilt don't.
    # `.gitmodules` says where a submodule comes from, so point the submodule's
    # own remote back at it first. Nothing else reconciles the two, and an
    # `origin` left pointing somewhere else is how odoo/src came to be upgraded
    # off a month-old ref.
    paths = [submodule.path for submodule in upgrading]
    git.sync_submodules(paths)
    git.register_submodules(paths)
    _run_submodule_tasks(
        {
            submodule.path: partial(_upgrade_task, submodule, force_branch)
            for submodule in upgrading
        },
        jobs=jobs,
        title="Upgrading submodules to their latest remote commit",
    )


def _confirm_branch(submodule, odoo_version):
    """Whether to go ahead with a submodule tracking something other than the
    project's Odoo version -- usually a mistake, occasionally deliberate."""
    if not submodule.branch or submodule.branch == odoo_version:
        return True
    ui.echo(
        f"WARNING: {submodule.path} branch is {submodule.branch}"
        f" (expected {odoo_version})"
    )
    return ui.ask_confirmation(f"Upgrade {submodule.path} anyway?")


def _rebuild_task(repo, target_branch, progress):
    progress.set_status("aggregating")
    repo.rebuild_consolidation_branch(push=True, target_branch=target_branch)


def _upgrade_task(submodule, branch, progress):
    progress.set_status("updating")
    git.submodule_update(submodule.path, submodule=submodule)
    try:
        progress.set_status("upgrading")
        git.submodule_upgrade(submodule.path, submodule.url, branch=branch)
    except Exception:
        # Put it back where it was before giving up: a half-upgraded submodule
        # is worse than one that was left alone. The failure is still reported
        # -- rolling back is not succeeding.
        progress.set_status("rolling back")
        git.submodule_update(submodule.path, submodule=submodule)
        raise


if __name__ == "__main__":
    cli()
