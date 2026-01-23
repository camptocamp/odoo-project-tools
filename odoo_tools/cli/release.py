# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import re

import click

from ..exceptions import ProjectConfigException
from ..utils.config import config
from ..utils.git import get_current_branch
from ..utils.marabunta import MarabuntaFileHandler
from ..utils.misc import get_ini_cfg_key
from ..utils.os_exec import run
from ..utils.path import build_path
from ..utils.pending_merge import push_branches

END_TIPS = [
    "Please continue with the release by:",
    " * Checking the diff",
    " * Running:",
    "\tgit add ... # pick the files",
    '\tgit commit -m "Release {version}"',
    "\tgit tag -a {version}  # optionally -s to sign the tag",
    "\t# copy-paste the content of the release from HISTORY.rst in the annotation of the tag",
    "\tgit push origin {branch} --tags",
]


def get_new_version_from_output(output):
    """Extract new version from bump-my-version output.

    Parses output like "New version will be '2.0.0'" from verbose mode.
    """
    match = re.search(r"New version will be '([^']+)'", output)
    if match:
        return match.group(1)
    # Fallback to old format for backwards compatibility
    return get_bumpversion_cfg_key(output, "new_version")


def get_bumpversion_cfg_key(cfg_content, key):
    return get_ini_cfg_key(cfg_content, "bumpversion", key)


def make_bumpversion_cmd(rel_type, new_version=None, dry_run=False):
    cmd = ["bump-my-version", "bump"]
    if new_version:
        cmd.append(f"--new-version {new_version}")
    if dry_run:
        cmd.append("--dry-run --verbose")
    cmd.append(rel_type)
    return " ".join(cmd)


def make_towncrier_cmd(version):
    return f"towncrier build --yes --version={version}"


def update_marabunta_file(version):
    if config.marabunta_mig_file_rel_path is None:
        raise ProjectConfigException(
            "Configure the marabunta_mig_file_rel_path in the project configuration file."
        )
    marabunta_file = build_path(config.marabunta_mig_file_rel_path)
    handler = MarabuntaFileHandler(marabunta_file)
    handler.update(version)


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--type",
    "rel_type",
    help="version increment to use",
    type=click.Choice(["major", "minor", "patch"], case_sensitive=False),
)
@click.option("--new-version", "new_version", help="explicit new version to create")
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="only display the version number which would be generated",
)
# @click.option("--commit/--no-commit", default=False, help="if set, then the changes are committed, otherwise you will need to do it yourself. ")
def bump(rel_type, new_version=None, dry_run=False, commit=False):
    """Prepare a new release"""
    cmd = make_bumpversion_cmd(rel_type, new_version=new_version, dry_run=dry_run)
    res = run(cmd, check=True, verbose=True)
    new_version = get_bumpversion_cfg_key(res, "new_version").strip()

    if dry_run:
        new_version = get_new_version_from_output(res).strip()
        click.echo(f"New version: {new_version}")
        return

    cmd = make_towncrier_cmd(new_version)
    run(cmd, check=True, verbose=True)

    if config.marabunta_mig_file_rel_path:
        click.echo("Updating marabunta migration file")
        update_marabunta_file(new_version)

    if click.confirm("Push local branches?"):
        push_branches(version=new_version)

    # TODO + run pip freeze and override requirements.txt
    # docker compose build --build-arg DEV_MODE=1 odoo
    # doco --rm run odoo pip freeze > requirements.txt

    branch = get_current_branch()
    if branch and new_version:
        end_tips = "\n".join(END_TIPS).format(branch=branch, version=new_version)
        click.echo(end_tips)


if __name__ == "__main__":
    cli()
