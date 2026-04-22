# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


import click

from ..utils import req as req_utils
from ..utils import ui
from ..utils.click import version_option
from ..utils.config import config
from ..utils.misc import SmartDict
from ..utils.path import build_path, is_odoo_module
from ..utils.proj import get_odoo_serie
from ..utils.pypi import odoo_name_to_pkg_name


@click.group()
@version_option
def cli():
    pass


@cli.command(name="add-req")
@click.argument("name")
@click.option("-v", "--version", "version")
@click.option("-p", "--pr", "pr")
@click.option("-b", "--branch", "branch")
@click.option("-r", "--repo-name", "repo_name")
@click.option("-u", "--upstream", "upstream")
@click.option("-f", "--file", "file", help="file to add the requirement to")
@click.option(
    "--odoo/--no-odoo",
    "odoo",
    default=True,
    help="use --no-odoo to install a python module which is not an Odoo addon",
)
def add_requirement(name, **kw):
    """Generate a python requirement line.

    You can simply copy the output and paste it in a requirements.txt file
    or pass the --file option to append it to a file.

    Example for a simple requirement line:

        otools-addon add-req edi_oca -v 18 -f dev-requirements.txt

    Example for a PR:

        otools-addon add-req edi_oca -v 18 -p $pr_ref -f test-requirements.txt
    """
    opts = SmartDict(kw)

    pkg_name = odoo_name_to_pkg_name(name, odoo_serie=get_odoo_serie())

    if opts.file:
        req_utils.add_requirement(
            pkg_name, pr=opts.pr, req_filepath=opts.file, version=opts.version
        )
        click.secho(f"Requirement line for {name} add to {opts.file}", fg="green")

    else:
        if opts.pr:
            line = req_utils.make_requirement_line_for_pr(
                pkg_name, opts.pr, use_wool=opts.use_wool
            )
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


@cli.command()
@click.argument("name")
def where(name):
    """Locate an addon by name across the project's addon directories."""
    search_paths = []
    local_src = build_path(config.local_src_rel_path)
    ext_src = build_path(config.ext_src_rel_path)
    odoo_src = build_path(config.odoo_src_rel_path)
    # local-src: direct children
    search_paths.append(local_src / name)
    # external-src: children of subdirectories (each subdir is a repo)
    if ext_src.is_dir():
        for repo_dir in sorted(ext_src.iterdir()):
            if repo_dir.is_dir():
                search_paths.append(repo_dir / name)
    # Odoo community addons
    search_paths.append(odoo_src / "addons" / name)
    # Odoo base addons
    search_paths.append(odoo_src / "odoo" / "addons" / name)

    found = [path for path in search_paths if is_odoo_module(path)]
    if not found:
        ui.exit_msg(f"Addon '{name}' not found")
    for path in found:
        click.echo(path)


if __name__ == "__main__":
    cli()
