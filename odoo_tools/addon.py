# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from .utils.pypi import get_last_pypi_version, odoo_name_to_pkg_name
from .utils.req import add_requirement, allowed_version, get_addon_requirement


@click.group()
def cli():
    pass


# tool 2:     install an OCA addon in a released version
# odoo-tools addon.add <github URL of the OCA addon>
# Check the latest version of the module on pypi, and use that version in the requirements.txt.

# If the module is already present in the requirements.txt file:
#     if the version is the same, do nothing. Otherwise, prompt the user to see
#     if the version has to be updated and act accordingly.
# If the addon is present as a PR (see below), prompt to confirm that the PR was merged
# and we want to work with the new version.
# Add a TODO in the implementation for a check on the dependencies of the module
# (we won't deal with this in this first implementation. Manifestoo could be used here.)


@cli.command()
@click.argument("name")
@click.option("-v", "--version", "version")
@click.option("-p", "--pr", "pr")
@click.option("-r", "--root-path", "root_path")
def add(name, version=None, pr=None, root_path=None):
    click.secho(f"Adding {name}", fg="green")
    current_req = get_addon_requirement(name)
    if not version:
        version = get_last_pypi_version(name)
        click.echo(f"Last pypi version {version}")

    # Not yet present
    if not current_req:
        add_requirement(odoo_name_to_pkg_name(name), version=version, pr=pr)
        click.echo("Requirements updated")
        return

    if current_req.local_file:
        # req = "-e path/to/project"
        # TODO
        pass

    if current_req.editable:
        # got a pending merge
        pass

    # check version
    is_ok = allowed_version(current_req, version)
    if is_ok:
        # TODO
        pass


if __name__ == "__main__":
    cli()
