# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click
from git import Repo as GitRepo
from rich.console import Console
from rich.prompt import Confirm

from ..exceptions import ProjectConfigException
from ..utils.click import global_command_decorators
from ..utils.config import config
from ..utils.git import get_current_branch, tag_signing_enabled
from ..utils.marabunta import MarabuntaFileHandler
from ..utils.os_exec import run
from ..utils.path import build_path
from ..utils.pending_merge import push_branches
from ..utils.proj import get_current_version, get_project_bundle_addon_name

console = Console()


def get_new_release_notes(repo, history_path):
    """Return the release notes towncrier just added to HISTORY.rst.

    Reads the diff of HISTORY.rst against HEAD (towncrier only inserts lines)
    and drops the title (the ``<version> (<date>)`` line and its underline).
    """
    diff = repo.git.diff("HEAD", "--", history_path.as_posix())
    added = []
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("+"):
            added.append(line[1:])
    # Drop blank seam lines, then the title line and its underline
    while added and not added[0].strip():
        added.pop(0)
    return "\n".join(added[2:]).strip()


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
@global_command_decorators
def cli():
    pass


@cli.command(help="Increment version")
@click.argument(
    "rel_type", type=click.Choice(["major", "minor", "patch"], case_sensitive=False)
)
@click.option("--new-version", "new_version", help="explicit new version to create")
@click.option(
    "--commit/--no-commit",
    "do_commit",
    default=None,
    help="Create the release commit",
)
@click.option(
    "--tag/--no-tag",
    "do_tag",
    default=None,
    help="Create the <VERSION> tag. Implies commit.",
)
@click.option(
    "--push-aggregated-branches/--no-push-aggregated-branches",
    "push_aggregated_branches",
    default=None,
    help="Push the aggregated (pending-merge) branches to upstream.",
)
def bump(  # noqa: C901
    rel_type,
    new_version=None,
    do_commit=None,
    do_tag=None,
    push_aggregated_branches=None,
):
    """Prepare a new release"""
    # --tag requires --commit (only the explicit conflict is an error here;
    # the undecided None cases are resolved by prompting later)
    if do_tag is True and do_commit is False:
        raise click.UsageError(
            "--tag requires --commit; --tag --no-commit is not allowed."
        )
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
    # Fail early on a dirty tree when we (likely) intend to commit
    if do_commit is not False and repo.is_dirty(untracked_files=True):
        raise click.ClickException(
            "There are uncommitted changes in the working tree. "
            "Commit or stash them before running `bump`."
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
    # Stage the version files
    repo.index.add(files)
    # Obtain the new version after the bump
    new_version = get_current_version()
    # Run towncrier to transform changelog into release notes
    cmd = make_towncrier_cmd(new_version)
    run(cmd, check=True, verbose=True)
    # Stage the changelog changes towncrier produced (HISTORY.rst + consumed fragments)
    history_path = build_path("HISTORY.rst")
    repo.index.add([history_path.as_posix(), build_path("changes.d").as_posix()])
    # Obtain the release notes from the HISTORY.rst diff
    release_notes = get_new_release_notes(repo, history_path)
    # Update the marabunta migration file with the new version
    if config.marabunta_mig_file_rel_path:
        update_marabunta_file(new_version)
        repo.index.add([build_path(config.marabunta_mig_file_rel_path).as_posix()])
    # Push the aggregated (pending-merge) branches to upstream
    if push_aggregated_branches is None:
        push_aggregated_branches = Confirm.ask(
            "Push aggregated branches?", default=True
        )
    if push_aggregated_branches:
        push_branches(version=new_version, force=True)
    # Resolve the commit decision now that the release files are ready to review
    if do_commit is None:
        do_commit = Confirm.ask("Create the release commit?", default=True)
    if do_commit:
        # Everything modified by the release process must be staged at this point
        if repo.is_dirty(index=False, untracked_files=True):
            raise click.ClickException(
                "Unexpected changes left in the working tree after staging the "
                "release files; aborting."
            )
        repo.index.commit(f"Release {new_version}")
        click.echo(f'✅ Committed "Release {new_version}"')
        # Resolve the tag decision
        if do_tag is None:
            do_tag = Confirm.ask("Create the release tag?", default=True)
        if do_tag:
            # If the tag already exists, ask before replacing it
            recreate = True
            if new_version in [tag.name for tag in repo.tags]:
                recreate = Confirm.ask(
                    f'Tag "{new_version}" already exists. Re-create it?',
                    default=True,
                )
            if recreate:
                repo.create_tag(
                    new_version,
                    message=release_notes,
                    sign=tag_signing_enabled(repo),
                    force=True,
                )
                click.echo(f'✅ Created tag "{new_version}"')
    # Print manual instructions for pending steps
    steps = []
    if not do_commit:
        steps.append(f'git commit -m "Release {new_version}"')
    if not do_tag:
        steps.append(
            f"git tag -a {new_version}  "
            "# add -s to sign; use the HISTORY.rst notes as the message"
        )
    # bump never pushes the commit/tag itself
    steps.append(f"git push --tags && git push origin {get_current_branch() or ''}")
    click.echo("Please continue the release by running:")
    for step in steps:
        click.echo(f"\t{step}")


if __name__ == "__main__":
    cli()
