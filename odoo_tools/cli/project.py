# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import re
import uuid

import click
import jinja2
from git import Repo as GitRepo

from ..utils import git, ui
from ..utils.config import PROJ_CFG_FILE, config
from ..utils.misc import (
    SmartDict,
    copy_file,
    get_docker_image_commit_hashes,
    get_template_path,
)
from ..utils.path import build_path
from ..utils.proj import (
    generate_odoo_config_file,
    get_current_version,
    get_project_bundle_addon_name,
    setup_venv,
)


def get_proj_tmpl_ver():
    ver = os.getenv("PROJ_TMPL_VER")
    if ver:
        ui.echo(f"Proj version override: {ver}", fg="red")
    return ver


def get_bumpversion_vars(opts):
    version = opts.version or get_current_version()
    odoo_major, odoo_minor, __ = version.split(".", 2)
    bundle_addon_manifest_rel_path = (
        config.local_src_rel_path / get_project_bundle_addon_name() / "__manifest__.py"
    )
    res = {
        "rel_path_local_addons": config.local_src_rel_path.as_posix(),
        "rel_path_version_file": (
            config.version_file_rel_path.as_posix()
            if config.version_file_rel_path
            else None
        ),
        "rel_path_bundle_addon_manifest": (
            bundle_addon_manifest_rel_path.as_posix()
            if build_path(bundle_addon_manifest_rel_path).is_file()
            else None
        ),
        "current_version": version,
        "odoo_major": odoo_major,
        "odoo_minor": odoo_minor,
    }
    return res


def convert_history_to_towncrier(history_path):
    """Converts the history file from the deprecated format to the new towncrier format

    Essentially, it just removes the latests (unreleased) section, and moves each line
    to a new fragment file.
    """
    content = history_path.read_text()
    content_lines = content.splitlines()

    if ".. towncrier release notes start" in content_lines:  # pragma: no cover
        return  # Already converted

    ui.echo("Converting history file to towncrier format..")

    def find_section(content_lines, title) -> tuple[int | None, int | None]:
        """Finds the section in the content and returns the start and end line numbers"""
        start = None
        end = None
        max_idx = len(content_lines) - 1
        for i in range(len(content_lines)):
            # Identify the start of the section
            if (
                start is None
                and content_lines[i].strip() == title
                and i + 1 < max_idx
                and content_lines[i + 1].strip() == "+" * len(title)
            ):
                start = i
            # Identify the end of the section
            elif (
                start is not None
                and content_lines[i].strip()
                and content_lines[i + 1].strip() == "+" * len(content_lines[i].strip())
            ):
                end = i - 1
                break
        # Handle case where end is simply the end of the file
        if start is not None and end is None:
            end = max_idx
        return start, end

    start, end = find_section(content_lines, "latest (unreleased)")
    if start is None or end is None:
        ui.echo(
            "No latest (unreleased) section found in history file. Skipping conversion.\n"
            "You will need to manually convert the history file to the towncrier format "
            "and create all the unreleased fragments in the changes.d directory.",
            fg="red",
        )
        return

    # Process each unreleased line and create a news fragment file for it
    section_map = {
        "Features and Improvements": "feat",
        "Bugfixes": "bug",
        "Documentation": "doc",
        "Build": "build",
    }
    section = None
    for line in content_lines[start + 2 : end]:
        # Identify current section header
        if match := re.match(r"\*\*(.*?)\*\*", line.strip()):
            section = match.group(1)
        # If the line is an item, move to a news fragment file
        elif match := re.match(
            r"\* (?:(?P<name>[A-Z][A-Z\d]+-[1-9]\d*): )?(?P<description>.*)",
            line.strip(),
        ):
            fragment_type = section_map.get(section, "misc")
            fragment_name = match.group("name") or str(uuid.uuid4()).split("-")[0]
            fragment_description = match.group("description") or ""
            fragment_path = build_path(f"./changes.d/{fragment_name}.{fragment_type}")
            fragment_path.parent.mkdir(parents=True, exist_ok=True)
            fragment_path.write_text(fragment_description + "\n")
            ui.echo(f"- Created fragment: {fragment_name}.{fragment_type}")

    # Remove the section and replace with the new lines
    template_content = get_template_path("HISTORY.tmpl.rst").read_text()
    template_content_lines = template_content.splitlines()

    # Replace everything up until the end of the last unreleased section with the new
    # lines coming from the template.
    new_content = (
        template_content_lines + [""] + content_lines[end + 1 :]
        if end + 1 < len(content_lines)
        else template_content_lines
    )

    # Write the new content
    history_path.write_text("\n".join(new_content) + "\n")


def get_init_template_files():
    return (
        {
            "source": f".proj.v{get_proj_tmpl_ver()}.cfg",
            "destination": build_path(f"./{PROJ_CFG_FILE}"),
            "check": lambda source_path, dest_path: not dest_path.exists(),
        },
        {
            "source": "docker-compose.override.tmpl.yml",
            "destination": build_path("./docker-compose.override.yml"),
        },
        {
            "source": ".bumpversion.tmpl.cfg",
            "destination": build_path("./.bumpversion.cfg"),
            "variables_getter": get_bumpversion_vars,
            "check": lambda source_path, dest_path: not dest_path.exists(),
            "backup": False,
        },
        {
            "source": "towncrier.tmpl.toml",
            "destination": build_path("./towncrier.toml"),
            "check": lambda source_path, dest_path: not dest_path.exists(),
        },
        {
            "source": ".towncrier-template.tmpl.rst",
            "destination": build_path(".towncrier-template.rst"),
            "check": lambda source_path, dest_path: not dest_path.exists(),
        },
        {
            "source": "HISTORY.tmpl.rst",
            "destination": build_path("./HISTORY.rst"),
            "check": lambda source_path, dest_path: not dest_path.exists(),
            "fallback": lambda source_path, dest_path: convert_history_to_towncrier(
                dest_path
            ),
        },
    )


def _backup(dest):
    backup_dest = dest.with_suffix(f"{dest.suffix}.bak")
    ui.echo(f"Backing up existing file {dest} to {backup_dest}")
    copy_file(dest, backup_dest)


def bootstrap_files(opts):
    # Generate specific templated files

    for item in get_init_template_files():
        source = get_template_path(item["source"])
        dest = item["destination"]
        check = item.get("check", lambda *p: True)
        if not check(source, dest):
            if "fallback" in item:
                item["fallback"](source, dest)
            continue
        if var_getter := item.get("variables_getter"):
            jinja_template = jinja2.Template(source.read_text(), trim_blocks=True)
            content = jinja_template.render(var_getter(opts))
        else:
            content = source.read_text()
        # Write the file, except if the target already matches the expected content
        if dest.exists() and dest.read_text() == content:
            continue
        elif opts.backup and item.get("backup", True) and dest.exists():
            _backup(dest)
        dest.write_text(content)

    # towncrier stuff TODO: move to odoo-template?
    path = build_path("./changes.d/.gitkeep")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "-v",
    "--version",
    "version",
    help="Use 1 for a project using the 'old image' format, and 2 for 'new image'",
)
@click.option(
    "-b",
    "--backup",
    "backup",
    help="Backup existing files before overriding them",
    is_flag=True,
    default=True,
)
def init(**kw):
    """Initialize a project"""
    click.echo("Preparing project...")
    bootstrap_files(SmartDict(kw))


@cli.command()
@click.option(
    "--odoo-hash",
    type=str,
    help="the commit hash to use for Odoo core. If not provided the docker image will be introspected.",
)
@click.option(
    "--enterprise-hash",
    type=str,
    help="the commit hash to use for Odoo Enterprise. If not provided the docker image will be introspected.",
)
@click.option(
    "--venv/--no-venv",
    type=bool,
    default=False,
    help="setup a virtual environment usable to work without docker",
)
@click.option(
    "--venv-path",
    type=str,
    default=".venv",
    help="Directory to use for the virtualenv",
)
def checkout_local_odoo(
    odoo_hash=None, enterprise_hash=None, venv=False, venv_path=".venv"
):
    """checkout odoo core and odoo enterprise in the working directory

    This can be used to test odoo core/enterprise patches inside docker (the tool will suggest how to change your
    docker-compose file to mount the checkouts inside the image), or to develop without Docker using the same version
    as the one used in the image.

    To develop without Docker you can call:
    `otools-project checkout-local-odoo --venv --venv-path=.venv`

    This will setup or update a virtual environment in the directory with the required tools installed to run Odoo
    locally (you will still need docker to get the correct versions of the source code, unless you pass the hashes
    on the command line).
    """
    if config.template_version == 1:
        ui.exit_msg("This command is not support on this project version;")
    odoo_src_dest = config.odoo_src_rel_path / "odoo"
    enterprise_src_dest = config.odoo_src_rel_path / "enterprise"
    if odoo_hash is None or enterprise_hash is None:
        image_odoo_hash, image_enterprise_hash = get_docker_image_commit_hashes()
        odoo_hash = odoo_hash or image_odoo_hash
        enterprise_hash = enterprise_hash or image_enterprise_hash
    if odoo_hash:
        git.get_odoo_core(odoo_hash, dest=odoo_src_dest)
    else:
        ui.exit_msg("Unable to find the commit hash of odoo core")

    if enterprise_hash:
        git.get_odoo_enterprise(enterprise_hash, dest=enterprise_src_dest)
    else:
        ui.exit_msg("Unable to find the commit hash of odoo enterprise")

    # Apply odoo/enterprise patches
    # This matches the behavior of the `001_apply_patches` script in the odoo-template
    # https://github.com/camptocamp/odoo-template/blob/99931bbc/%7B%7Bcookiecutter.repo_name%7D%7D/build.d/001_apply_patches
    patches_dir = build_path("./patches")
    if patches_dir.is_dir():
        for patch in patches_dir.glob("**/*.patch"):
            patch_target = (
                config.odoo_src_rel_path / patch.relative_to(patches_dir).parent
            )
            ui.echo(f"Applying patch {patch.name} to {patch_target}")
            target_repo = GitRepo(build_path(patch_target))
            target_repo.git.am("--3way", patch)

    if venv:
        setup_venv(venv_path)
        generate_odoo_config_file(venv_path, odoo_src_dest, enterprise_src_dest)
        ui.echo("\nOdoo is now installed and available in `{venv}/bin/odoo`")
    else:
        ui.echo(
            "\nYou can add the following lines to docker-compose.override.yml, in the odoo service section:"
        )
        ui.echo(
            """
    volumes:
      - "./src/odoo:/odoo/src/odoo"
      - "./src/enterprise:/odoo/src/enterprise"
      """
        )
        ui.echo(
            """
Then run:

docker compose run --rm odoo pip install --user -e /odoo/src/odoo
"""
        )


if __name__ == "__main__":
    cli()
