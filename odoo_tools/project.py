# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

import click

from .config import PROJ_CFG_FILE, get_conf_key
from .utils.misc import SmartDict, copy_file, get_template_path
from .utils.os_exec import run
from .utils.path import build_path
from .utils.proj import get_project_manifest_key


def get_proj_tmpl_ver():
    return os.getenv("PROJ_TMPL_VER", "2")


def get_bumpversion_vars(opts):
    # TODO: get version from version file as default
    version = opts.version or get_project_manifest_key("odoo_version") + ".0.1.0"
    odoo_major, odoo_minor, __ = version.split(".", 2)
    res = {
        "rel_path_local_addons": get_conf_key("local_src_rel_path").as_posix(),
        "rel_path_version_file": get_conf_key("version_file_rel_path").as_posix(),
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
@click.option("-v", "--version", "version")
def init(**kw):
    click.echo("Preparing project...")
    bootstrap_files(SmartDict(kw))


if __name__ == '__main__':
    cli()
