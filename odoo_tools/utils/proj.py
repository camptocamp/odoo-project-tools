# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import os
import shutil
import subprocess
import venv
from functools import cache

from ..config import get_conf_key
from . import ui
from .misc import get_template_path
from .path import build_path, get_root_marker, root_path
from .yaml import yaml_load


@cache
def get_project_manifest(key=None):
    path = root_path() / get_root_marker()
    with open(path) as f:
        return yaml_load(f.read())


def get_project_manifest_key(key):
    return get_project_manifest()[key]


def get_current_version(serie_only=False):
    ver_file = build_path(get_conf_key("version_file_rel_path"))
    with ver_file.open() as fd:
        ver = fd.read().strip()
    if serie_only:
        ver = ver.split(".")[0]
    return ver


def setup_venv(venv_dir, odoo_src_path=None):
    venv_dir = build_path(venv_dir)
    ensure_local_requirements(build_path("local-requirements.txt"))
    if (venv_dir / "pyvenv.cfg").is_file():
        ui.echo(f"Reusing existing venv {venv_dir}")
    else:
        venv.create(venv_dir, with_pip=True)
    pip = venv_dir / "bin/pip"
    if odoo_src_path is None:
        odoo_src_path = build_path(get_conf_key("odoo_src_rel_path"))

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
        database_name = os.path.dirname(root_path())
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
    with open(config_file) as odoo_cfg:
        for line in odoo_cfg:
            if line.strip().startswith("running_env"):
                config_has_running_env = True
                break
    if not config_has_running_env:
        with open(config_file, "a+") as odoo_cfg:
            odoo_cfg.write("\nrunning_env=dev\n")
