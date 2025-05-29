from itertools import chain

import click

from ..utils import git, path, proj, ui
from ..utils import pending_merge as pm_utils


@click.group()
def cli():
    pass


@cli.command()
@click.pass_context
def init(ctx):
    """Add git submodules read in the .gitmodules files.

    Allows to edit the .gitmodules file, add all the repositories and
    run the command once to add all the submodules.

    It means less 'git submodule add -b ... {url} {path}' commands to run

    """
    with path.cd(path.root_path()):
        for submodule in git.iter_gitmodules():
            git.submodule_init(submodule)

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
        blacklist = {"odoo/src"}
        lines = (f"odoo/{line}" for line in submodules if line not in blacklist)
        lines = chain(
            [
                "odoo/src/odoo/odoo/addons",
                "odoo/src/odoo/addons",
                "odoo/src/enterprise",
                "odoo/odoo/addons",
            ],
            lines,
            ["odoo/odoo/paid-modules"],
        )
        lines = ("/%s" % line for line in lines)
        template = 'ENV ADDONS_PATH="%s" \\\n'
        print(template % (", \\\n".join(lines)))
    else:
        for line in submodules:
            ui.echo(line)


@cli.command()
@click.argument("submodule_path", default="")
def update(submodule_path=None):
    """Initialize or update submodules

    Synchronize submodules and then launch `git submodule update --init`
    for each submodule.

    If `git-autoshare` is configured locally, it will add `--reference` to
    fetch data from local cache.

    :param submodule_path: submodule path for a precise sync & update

    """
    with path.cd(path.root_path()):
        for submodule in git.iter_gitmodules(filter_path=submodule_path):
            git.submodule_sync(submodule.path)
            git.submodule_update(submodule.path)


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
    repo = repo or pm_utils.Repo(submodule_path)

    new_remote_url = pm_utils.get_new_remote_url(repo=repo, force_remote=force_remote)

    git.set_remote_url(repo.path, new_remote_url)

    print(f"Submodule {repo.path} is now being sourced from {new_remote_url}")

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
            with path.cd(repo.abs_path):
                git.checkout(target_branch=odoo_version)


if __name__ == "__main__":
    cli()
