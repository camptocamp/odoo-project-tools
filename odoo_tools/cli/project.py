# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

import click

from ..config import PROJ_CFG_FILE, load_config
from ..utils import git, ui
from ..utils.misc import (
    SmartDict,
    copy_file,
    get_docker_image_commit_hashes,
    get_template_path,
)
from ..utils.os_exec import run
from ..utils.path import build_path
from ..utils.proj import (
    generate_odoo_config_file,
    get_current_version,
    get_project_manifest_key,
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
    config = load_config()
    res = {
        "rel_path_local_addons": config.local_src_rel_path.as_posix(),
        "rel_path_version_file": config.version_file_rel_path.as_posix(),
        "bundle_addon_name": "{}_bundle".format(
            get_project_manifest_key("customer_shortname")
        ),
        "current_version": version,
        "odoo_major": odoo_major,
        "odoo_minor": odoo_minor,
    }
    return res


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
        },
        {
            "source": "towncrier.tmpl.toml",
            "destination": build_path("./towncrier.toml"),
        },
        {
            "source": ".towncrier-template.tmpl.rst",
            "destination": build_path(".towncrier-template.rst"),
        },
    )


def bootstrap_files(opts):
    # Generate specific templated files
    for item in get_init_template_files():
        source = get_template_path(item["source"])
        dest = item["destination"]
        check = item.get("check", lambda *p: True)
        if not check(source, dest):
            continue
        var_getter = item.get("variables_getter")
        if var_getter:
            with open(source) as source_fd:
                content = source_fd.read()
                # TODO: use better variable tmpl?
                for k, v in var_getter(opts).items():
                    content = content.replace(f"${k}", v)
                    # avoid errors from end-of-file-fixer in pre-commit
                    content = content.rstrip("\n") + "\n"
                with open(dest, "w") as dest_fd:
                    dest_fd.write(content)
        else:
            copy_file(source, dest)

    # towncrier stuff TODO: move to odoo-template?
    path = build_path("./changes.d/.gitkeep")
    if not path.exists():
        os.makedirs(path.parent, exist_ok=True)
        run(f"touch {path}")


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
    config = load_config()
    if config.template_version == 1:
        ui.exit_msg("This command is not support on this project version;")
    version = get_current_version(serie_only=True)
    branch = f"{version}.0"
    odoo_src_dest = config.odoo_src_rel_path / "odoo"
    enterprise_src_dest = config.odoo_src_rel_path / "enterprise"
    if odoo_hash is None or enterprise_hash is None:
        image_odoo_hash, image_enterprise_hash = get_docker_image_commit_hashes()
        odoo_hash = odoo_hash or image_odoo_hash
        enterprise_hash = enterprise_hash or image_enterprise_hash
    if odoo_hash:
        git.get_odoo_core(odoo_hash, dest=odoo_src_dest, branch=branch)
    else:
        ui.exit_msg("Unable to find the commit hash of odoo core")

    if enterprise_hash:
        git.get_odoo_enterprise(
            enterprise_hash, dest=enterprise_src_dest, branch=branch
        )
    else:
        ui.exit_msg("Unable to find the commit hash of odoo enterprise")

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
