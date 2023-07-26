# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from .config import get_conf_key
from .utils.marabunta import MarabuntaFileHandler
from .utils.misc import get_ini_cfg_key
from .utils.os_exec import run
from .utils.path import build_path
from .utils.pending_merge import push_branches


def get_bumpversion_cfg_key(cfg_content, key):
    return get_ini_cfg_key(cfg_content, "bumpversion", key)


def make_bumpversion_cmd(rel_type, new_version=None, dry_run=False):
    cmd = ["bumpversion"]
    if new_version:
        cmd.append(f"--new-version {new_version}")
    if dry_run:
        cmd.append("--dry-run --list")
    cmd.append(rel_type)
    return " ".join(cmd)


def make_towncrier_cmd(version):
    return "towncrier build --yes --version={}".format(version)


def update_marabunta_file(version):
    marabunta_file = build_path(get_conf_key("marabunta_mig_file_rel_path"))
    handler = MarabuntaFileHandler(marabunta_file)
    handler.update(version)


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--type",
    "rel_type",
    type=click.Choice(['major', 'minor', 'patch'], case_sensitive=False),
)
@click.option("--new-version", "new_version")
@click.option("--dry-run", "dry_run", is_flag=True)
@click.option("--commit/--no-commit", default=False)
def bump(rel_type, new_version=None, dry_run=False, commit=False):
    cmd = make_bumpversion_cmd(rel_type, new_version=new_version, dry_run=dry_run)
    click.echo(f"Running: {cmd}")
    res = run(cmd)
    if dry_run:
        new_version = get_bumpversion_cfg_key(res, "new_version").strip()
        click.echo(f"New version: {new_version}")
        return
    with get_conf_key("version_file_rel_path").open() as fd:
        new_version = fd.read().strip()

    cmd = make_towncrier_cmd(new_version)
    click.echo(f"Running: {cmd}")
    run(cmd)
    click.echo("Updating marabunta migration file")
    update_marabunta_file(new_version)

    if click.confirm("Push local branches?"):
        push_branches(version=new_version)


if __name__ == '__main__':
    cli()
