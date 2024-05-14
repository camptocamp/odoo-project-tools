# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from ..utils import pending_merge as pm_utils
from ..utils import req as req_utils
from ..utils import ui
from ..utils.misc import SmartDict
from ..utils.os_exec import run
from ..utils.pkg import Package
from ..utils.proj import get_current_version
from ..utils.pypi import odoo_name_to_pkg_name


# TODO: centralize ask/confirm/abort in `ui` utils
def ask_confirm_replace(pkg, msg, version=None):
    if click.confirm(msg, abort=True):
        pkg.replace_requirement(version=version)
        click.echo("Requirement replaced")
        raise click.exceptions.Exit(0)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("name")
@click.option(
    "-v", "--version", "version", help="the version of the addon you want to install"
)
@click.option("-p", "--pr", "pr", help="the URL of the pull request you want to add")
@click.option(
    "--odoo/--no-odoo",
    "odoo",
    default=True,
    help="use --no-odoo to install a python module which is not an Odoo addon",
)
@click.option(
    "--upgrade",
    "upgrade",
    is_flag=True,
    default=False,
    help="upgrade will update the addon to the latest available version on PyPI",
)
def add(name, version=None, pr=None, odoo=True, upgrade=False):
    """Update the project's requirements for a given package (odoo or not).

    * If the module is not already listed in the requirements.txt, check the
      latest version of the module on PyPI and use that version

    * Otherwise:

        * if the version is the same, do nothing. Otherwise, prompt the user
        * If the addon is present as a PR, prompt the user

    """
    # TODO: centralize printing/logging in `ui` utils
    click.secho(f"Adding: {name}", fg="green")
    pkg = Package(name, odoo=odoo)
    click.echo(f"Last PyPI version: {pkg.latest_version}")

    if not pkg.pinned_version:
        # Brand new module: just add it
        pkg.add_requirement(version=version, pr=pr)
        click.echo("Requirement updated")
        raise click.exceptions.Exit(0)

    click.echo(f"Pinned version: {pkg.pinned_version}")
    if upgrade:
        prompt = f"Are you sure you want to upgrade to {pkg.latest_version}?"
        ask_confirm_replace(pkg, prompt, version=version)

    # check version
    if version and not pkg.allowed_version(version):
        prompt = f"Pinned version(s): {pkg.pinned_version}. Are you sure you want to change version?"
        ask_confirm_replace(pkg, prompt, version=version)

    # Has a PR
    if pkg.has_pending_merge():
        prompt = f"Currently using a pending merge from {pkg.uri}. Are you sure you want to replace it?"
        ask_confirm_replace(pkg, prompt, version=version)

    # if current_req.local_file:
    #     # req = "-e path/to/project"
    #     # TODO
    #     pass

    # if current_req.editable:
    #     # got a local installation or a temporary pending merge
    #     # TODO
    #     pass

    # TODO: check on the dependencies of the module
    # (we won't deal with this in this first implementation. Manifestoo could be used here.)


@cli.command(name="add-pending")
@click.argument("pr_url")
@click.option("-a", "--addons", "addons", help="comma separated list of addon names")
@click.option(
    "--aggregate/--no-aggregate",
    "aggregate",
    help="run git aggregate. This is the default behavior.",
    is_flag=True,
    default=True,
)
@click.option(
    "--editable/--no-editable",
    "editable",
    help="install the addon in editable mode (pip install -e). This is the default behavior.",
    is_flag=True,
    default=True,
)
def add_pending(pr_url, addons=None, editable=True, aggregate=True):
    """Add a pending PR or commit.

    This command will create or update an aggregation file corresponding to the
    repository  in the pending-merges.d directory to add the specified.

    If the pr_url is really a pull request, then the pull request is aggregated.
    If it is a commit url, then the commit is cherry picked.

    If addons are listed, they are added to the dev-requirements.txt file."""

    pm_utils.add_pending(pr_url, aggregate=aggregate)

    addons = [x.strip() for x in addons.split(",") if x.strip()] if addons else []
    if not addons:
        ui.exit_msg("No addon specifified. Please update dev requirements manually.")

    ui.echo(f"Adding: {', '.join(addons)} from {pr_url}")

    # Create req file if missing
    dev_req_file_path = req_utils.get_project_dev_req()
    if not dev_req_file_path.exists():
        run(f"touch {dev_req_file_path.as_posix()}")

    for name in addons:
        pkg = Package(
            name,
            odoo=True,
            req_filepath=dev_req_file_path,
        )
        # TODO: does it work w/ commits?
        pkg.add_or_replace_requirement(pr=pr_url, editable=editable)

    ui.echo(f"Updated dev requirements for: {', '.join(addons)}", fg="green")

    # TODO: stage changes for commit


@cli.command(name="print-req")
@click.argument("name")
@click.option("-v", "--version", "version")
@click.option("-p", "--pr", "pr")
@click.option("-b", "--branch", "branch")
@click.option("-r", "--repo-name", "repo_name")
@click.option("-u", "--upstream", "upstream")
@click.option(
    "--odoo/--no-odoo",
    "odoo",
    default=True,
    help="use --no-odoo to install a python module which is not an Odoo addon",
)
def print_requirement(name, **kw):
    """Print requirement line."""
    opts = SmartDict(kw)
    pkg_name = odoo_name_to_pkg_name(
        name, odoo_serie=get_current_version(serie_only=True)
    )
    if opts.pr:
        line = req_utils.make_requirement_line_for_pr(pkg_name, opts.pr)
    elif opts.branch:
        if not opts.repo_name:
            ui.exit_msg("Repo name is required")
        line = req_utils.make_requirement_line_for_proj_fork(
            pkg_name, opts.repo_name, opts.branch, upstream=opts.upstream
        )
    else:
        line = req_utils.make_requirement_line(pkg_name, version=opts.version)

    click.secho(f"Requirement line for: {name}", fg="green")
    ui.echo("")
    ui.echo(line)
    ui.echo("")


if __name__ == "__main__":
    cli()
