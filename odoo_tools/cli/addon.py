# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from ..utils import pending_merge as pm_utils, ui
from ..utils.os_exec import run
from ..utils.pkg import Package
from ..utils.req import get_project_dev_req


@click.group()
def cli():
    pass


@cli.command()
@click.argument("name")
@click.option("-v", "--version", "version")
@click.option("-p", "--pr", "pr")
@click.option("-r", "--root-path", "root_path")
@click.option("-o", "--odoo", "odoo", default=True)
@click.option("--upgrade", "upgrade", is_flag=True, default=False)
def add(name, version=None, pr=None, root_path=None, odoo=True, upgrade=False):
    """Update project requirements for a given package (odoo or not).

    * Check the latest version of the module on pypi and use that version if new.
    * If the module is already present in the requirements.txt file:
        * if the version is the same, do nothing. Otherwise, prompt the user
        * If the addon is present as a PR prompt the user
    """
    # TODO: get odoo version from project
    # TODO: centralize printing/logging in `ui` utils
    click.secho(f"Adding: {name}", fg="green")
    pkg = Package(name, odoo=odoo)
    click.echo(f"Last pypi version: {pkg.latest_version}")

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
@click.argument("ref")
@click.option("-a", "--addons", "addons")
@click.option("--editable/--no-editable", "editable", is_flag=True, default=True)
def add_pending(ref, addons=None, editable=True):
    """Add a pending PR or commit."""
    pm_utils.add_pending(ref)
    click.secho(f"Adding: {ref}", fg="green")
    # TODO: run git-aggregate if already present
    addons = [x.strip() for x in addons.split(",") if x.strip()] if addons else []
    if not addons:
        ui.exit_msg("No addon specifified. Please update dev requirements manually.")

    # Create req file if missing
    dev_req_file_path = get_project_dev_req()
    if not dev_req_file_path.exists():
        run(f"touch {dev_req_file_path.as_posix()}")

    for name in addons:
        pkg = Package(name, odoo=True, req_filepath=dev_req_file_path)
        # TODO: does it work w/ commits?
        pkg.add_or_replace_requirement(pr=ref, editable=editable)

    ui.exit_msg(f"Updated dev requirements for: {', '.join(addons)}")

    # TODO: stage changes for commit


# TODO: centralize ask/confirm/abort in `ui` utils
def ask_confirm_replace(pkg, msg, version=None):
    if click.confirm(msg, abort=True):
        pkg.replace_requirement(version=version)
        click.echo("Requirement replaced")
        raise click.exceptions.Exit(0)


if __name__ == "__main__":
    cli()
