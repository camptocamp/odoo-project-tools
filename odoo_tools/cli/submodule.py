import click

from ..utils import git, path, ui


@click.group()
def cli():
    pass


@cli.command()
def init():
    """Add git submodules read in the .gitmodules files.

    Allows to edit the .gitmodules file, add all the repositories and
    run the command once to add all the submodules.

    It means less 'git submodule add -b ... {url} {path}' commands to run

    """
    with path.cd(path.root_path()):
        for line in git.iter_submodules():
            git.submodule_add(line)

    ui.echo("Submodules added")
    # ui.echo()
    # ui.echo("You can now update odoo/Dockerfile with this addons-path:")
    # ui.echo()
    # ls()


@cli.command()
@click.option(
    "--dockerfile/--no-dockerfile",
    default=True,
    help="With --no-dockerfile, the raw paths are listed instead of the Dockerfile format",
)
def ls(dockerfile=True):
    """[NOT IMPLEMENTED]List git submodules paths.

    It can be used to directly copy-paste the addons paths in the Dockerfile.
    The order depends of the order in the .gitmodules file.

    """
    pass


# @cli.command()
# @click.argument("submodule_path")
# @click.option("--push/--no-push", default=True)
# @click.option("-b", "--target-branch")
# def merges(submodule_path, push=True, target_branch=None):
#     """Regenerate a pending branch for a submodule.
#
#     Use case: a PR has been updated and you want to refresh it.
#
#     It reads pending-merges.d/sub-name.yml, runs gitaggregator on the submodule
#     and pushes the new branch on dynamic target constructed as follows:
#     camptocamp/merge-branch-<project_id>-<branch>-<commit>
#
#     By default, the branch is pushed on the camptocamp remote, but you
#     can disable the push with ``--no-push``.
#
#     Beware, if you changed the remote of the submodule manually, you still need
#     to run `sync_remote` manually.
#     """
#     ui.echo("Use otools-pending aggregate")
#


@cli.command()
@click.argument("submodule_path")
@click.option("-b", "--target-branch")
def push(submodule_path, target_branch=None):
    """[NOT IMPLEMENTED] Push a Submodule

    Pushes the current state of your submodule to the target remote and branch
    either given by you or specified in pending-merges.yml
    """
    pass


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
    submodule_info = git._get_submodules(submodule_path)
    with path.cd(path.root_path()):
        git.submodule_sync(submodule_path)
        git.submodule_update(submodule_info)


# @cli.command()
# @click.argument("submodule_path", default="")
# @click.argument("repository", default="")
# @click.option("--force-remote/--no-force-remote", default=False)
# def sync_remote(submodule_path=None, repo=None, force_remote=False):
#     ui.echo("Use otools-pending aggregate")
#

# To add
# * show prs -> otools-pending show
# * show closed prs -> otools-pending show
# * list_external_dependencies_installed
# * upgrade

if __name__ == "__main__":
    cli()
