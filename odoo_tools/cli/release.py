# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click
from git import Repo as GitRepo
from rich.console import Console

from ..exceptions import ProjectConfigException
from ..utils.click import version_option
from ..utils.config import config
from ..utils.git import get_current_branch
from ..utils.marabunta import MarabuntaFileHandler
from ..utils.os_exec import run
from ..utils.path import build_path
from ..utils.pending_merge import push_branches
from ..utils.proj import get_current_version, get_project_bundle_addon_name

console = Console()


END_TIPS = [
    "Please continue with the release by:",
    " * Checking the diff",
    " * Running:",
    '\tgit commit -m "Release {version}"',
    "\tgit tag -a {version}  # optionally -s to sign the tag",
    "\t# copy-paste the content of the release from HISTORY.rst in the annotation of the tag",
    "\tgit push --tags && git push origin {branch}",
]


def get_bumpversion_files():
    """Return the list of files that bump-my-version should update."""
    files = []
    # VERSION file
    if config.version_file_rel_path is not None:
        files.append(build_path(config.version_file_rel_path).as_posix())
    # Bundle addon
    local_src_path = build_path(config.local_src_rel_path)
    bundle_addon_name = get_project_bundle_addon_name()
    bundle_addon_path = local_src_path / bundle_addon_name
    bundle_addon_manifest = bundle_addon_path / "__manifest__.py"
    if bundle_addon_manifest.is_file():
        files.append(bundle_addon_manifest.as_posix())
    # pyproject.toml
    pyproject_toml = build_path("pyproject.toml")
    if pyproject_toml.is_file():
        files.append(pyproject_toml.as_posix())
    return files


def make_bumpversion_cmd(rel_type, current_version, files, new_version=None):
    parse = (
        r"(?P<odoo_major>\d+)\.(?P<odoo_minor>\d+)"
        r"\.(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    )
    serialize = "{odoo_major}.{odoo_minor}.{major}.{minor}.{patch}"
    cmd = [
        "bump-my-version",
        "bump",
        "--current-version",
        current_version,
        "--parse",
        parse,
        "--serialize",
        serialize,
        "--ignore-missing-files",
        "--ignore-missing-version",
    ]
    if new_version:
        cmd.extend(["--new-version", new_version])
    cmd.append(rel_type)
    cmd.extend(files)
    return cmd


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
@version_option
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
def bump(rel_type, new_version=None):
    """Prepare a new release"""
    repo = GitRepo(".")
    # Warn about deprecated .bumpversion.cfg file
    bumpversion_cfg = build_path(".bumpversion.cfg")
    if bumpversion_cfg.is_file():
        console.print(
            "Deprecated .bumpversion.cfg file found. It is not recommended to use it.\n"
            "Custom configuration is allowed, but it's recommended to do it in the "
            "pyproject.toml. See bump-my-version documentation for more details.",
            style="yellow",
        )
    # Obtain the list files where a version is written
    files = get_bumpversion_files()
    if not files:
        raise click.ClickException(
            "No files to bump. Configure a VERSION file or create a bundle addon."
        )
    # Bump the version
    current_version = get_current_version()
    cmd = make_bumpversion_cmd(
        rel_type,
        current_version,
        files,
        new_version=new_version,
    )
    run(cmd, check=True, verbose=True)
    repo.index.add(files)
    # Obtain the new version after the bump
    new_version = get_current_version()
    # Run towncrier to transform changelog into release notes
    cmd = make_towncrier_cmd(new_version)
    run(cmd, check=True, verbose=True)
    # Update the marabunta migration file with the new version
    if config.marabunta_mig_file_rel_path:
        click.echo("Updating marabunta migration file")
        update_marabunta_file(new_version)
        repo.index.add([build_path(config.marabunta_mig_file_rel_path)])
    # Push local branches to upstream
    if click.confirm("Push local branches?"):
        push_branches(version=new_version, force=True)
    # Print the manual actions to perform
    branch = get_current_branch()
    if branch and new_version:
        end_tips = "\n".join(END_TIPS).format(branch=branch, version=new_version)
        click.echo(end_tips)


if __name__ == "__main__":
    cli()
