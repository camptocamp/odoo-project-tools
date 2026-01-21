# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import shutil
import subprocess
import venv
from functools import cache

from . import ui
from .config import config
from .misc import get_ini_cfg_key, get_template_path
from .path import build_path, get_root_marker, root_path
from .yaml import yaml_load


@cache
def get_project_manifest(key=None):
    path = root_path() / get_root_marker()
    return yaml_load(path.read_text())


def get_project_manifest_key(key):
    return get_project_manifest()[key]


def get_odoo_version():
    return get_project_manifest_key("odoo_version")


def get_odoo_serie():
    return get_odoo_version().split(".")[0]


def get_current_version():
    """Gets the current project version

    Historically, we stored the version in the VERSION file.

    However, since we started using bumpversion it became sort of redundant with the
    bumpversion config file's `current_version` key. Moreover, projects generated with
    the `odoosh-template` do not have a VERSION file.

    This method will then try to identify the current version like so:

    - Read the bumpversion config file's `current_version` key
    - Fallback to the VERSION file, if it exists
    - Generate a new blank version on-the-fly "$ODOO_VERSION.0.0.0" otherwise
    """
    # Attempt to read from the bumpversion config file
    bumpversion_config_path = build_path(".bumpversion.cfg")
    if bumpversion_config_path.is_file():
        bumpversion_config = bumpversion_config_path.read_text()
        current_version = get_ini_cfg_key(
            bumpversion_config, "bumpversion", "current_version"
        )
        if current_version:
            return current_version
    # Fallback to the VERSION file, if it exists
    if config.version_file_rel_path is not None:
        version_file_path = build_path(config.version_file_rel_path)
        if version_file_path.is_file():
            return version_file_path.read_text().strip()
    # Generate a blank version on-the-fly: this is likely the case of new projects
    odoo_version = get_project_manifest_key("odoo_version")
    return f"{odoo_version}.0.0.0"


def setup_venv(venv_dir, odoo_src_path=None):
    venv_dir = build_path(venv_dir)
    ensure_local_requirements(build_path("local-requirements.txt"))
    if (venv_dir / "pyvenv.cfg").is_file():
        ui.echo(f"Reusing existing venv {venv_dir}")
    else:
        venv.create(venv_dir, with_pip=True)
    pip = venv_dir / "bin/pip"
    if odoo_src_path is None:
        odoo_src_path = build_path(config.odoo_src_rel_path)

    if not (venv_dir / "bin/odoo").is_file():
        subprocess.run(
            [pip, "install", "-r", odoo_src_path / "requirements.txt"], check=False
        )
        subprocess.run([pip, "install", "-r", "local-requirements.txt"], check=False)
    subprocess.run([pip, "install", "-r", build_path("requirements.txt")], check=False)
    if build_path("dev_requirements.txt").is_file():
        subprocess.run(
            [pip, "install", "-r", build_path("dev_requirements.txt")], check=False
        )
    subprocess.run([pip, "install", "-e", "."], check=False)


def ensure_local_requirements(local_requirement_path):
    local_requirement_tmpl = get_template_path("local-requirements.txt")
    if not local_requirement_path.is_file():
        shutil.copy(local_requirement_tmpl, local_requirement_path)
    # TODO handle locally modified local-requirements.txt


def generate_odoo_config_file(
    venv_dir,
    odoo_src_path,
    odoo_enterprise_path,
    config_file="odoo.cfg",
    database_name=None,
):
    if database_name is None:
        database_name = root_path().parent.name
    config_file = build_path(config_file)
    if config_file.is_file():
        ui.echo(f"Reusing existing configuration file {config_file}")
    else:
        odoo = build_path(venv_dir) / "bin/odoo"
        addons_dir = build_path("odoo/addons")

        subprocess.run(
            [
                odoo,
                "--save",
                "-c",
                config_file,
                "-d",
                database_name,
                f"--addons-path={addons_dir}, {odoo_enterprise_path},{odoo_src_path}/addons,{odoo_src_path}/odoo/addons",
                "--workers=0",
                "--stop-after-init",
            ],
            check=False,
        )
    config_has_running_env = False
    with config_file.open() as odoo_cfg:
        for line in odoo_cfg:
            if line.strip().startswith("running_env"):
                config_has_running_env = True
                break
    if not config_has_running_env:
        with config_file.open("a+") as odoo_cfg:
            odoo_cfg.write("\nrunning_env=dev\n")
