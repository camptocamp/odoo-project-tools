# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import configparser

import click

from .config import get_conf_key
from .utils import yaml
from .utils.os_exec import run
from .utils.path import build_path


def parse_bumpversion_cfg(ini_content):
    config = configparser.ConfigParser()
    # header gets stripped when you get new content via --dry-run --list
    header = "[bumpversion]"
    if header not in ini_content:
        ini_content = header + "\n" + ini_content
    config.read_string(ini_content)
    return config


def get_cfg_key(cfg_content, key):
    cfg = parse_bumpversion_cfg(cfg_content)
    return cfg.get("bumpversion", key)


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


class MarabuntFileHandler:
    def __init__(self, path_obj):
        self.path_obj = path_obj

    def load(self):
        return yaml.yaml_load(self.path_obj.open())

    def update(self, version, run_click_hook="pre"):
        data = self.load()
        versions = data["migration"]["versions"]
        version_item = [x for x in versions if x["version"] == version]
        if not version_item:
            version_item = {"version": version}
            versions.append(version_item)
        if not version_item.get("operations"):
            version_item["operations"] = {}
        operations = version_item["operations"]
        cmd = self._make_click_odoo_update_cmd()
        operations.setdefault(run_click_hook, []).append(cmd)
        yaml.update_yml_file(self.path_obj, data)

    def _make_click_odoo_update_cmd(self):
        return "click-odoo-update"


def update_marabunta_file(version):
    marabunta_file = build_path(get_conf_key("marabunta_mig_file_rel_path"))
    handler = MarabuntFileHandler(marabunta_file)
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
        new_version = get_cfg_key(res, "new_version")
        click.echo(f"New version: {new_version}")
    else:
        with get_conf_key("version_file_rel_path").open() as fd:
            new_version = fd.read()
        cmd = make_towncrier_cmd(new_version)
        click.echo(f"Running: {cmd}")
        run(cmd)
        click.echo("Updating marabunta migration file")
        update_marabunta_file(new_version)


if __name__ == '__main__':
    cli()
