# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import configparser
import shutil
from importlib.resources import files
from pathlib import Path

from . import docker_compose, os_exec

PKG_NAME = "odoo_tools"


def get_file_path(filepath):
    return files(PKG_NAME) / filepath


def get_template_path(filepath):
    return get_file_path(f"templates/{filepath}")


def get_cache_path():
    return Path.home() / ".cache" / "otools"


def copy_file(src_path, dest_path):
    shutil.copy(src_path, dest_path)


class SmartDict(dict):
    """Dotted notation dict."""

    def __getattr__(self, attrib):
        val = self.get(attrib)
        return self.__class__(val) if isinstance(val, dict) else val


def parse_ini_cfg(ini_content, header):
    config = configparser.ConfigParser()
    # header might get stripped when reading content from output
    # (eg: when using bumpversion)
    header = f"[{header}]"
    if header not in ini_content:
        ini_content = header + "\n" + ini_content
    config.read_string(ini_content)
    return config


def get_ini_cfg_key(cfg_content, header, key):
    cfg = parse_ini_cfg(cfg_content, header)
    return cfg.get(header, key)


def get_docker_image_commit_hashes():
    """Retrieve the odoo core and odoo enterprise commit hashes used in the project image"""
    output = os_exec.run(docker_compose.run("odoo", ["printenv"]))
    variables = {}
    for line in output.splitlines():
        try:
            name, value = line.strip().split("=", maxsplit=1)
        except ValueError:
            # not formatted as an environment variable, we can ignore
            continue
        variables[name] = value
    odoo_hash = variables.get("CORE_HASH")
    enterprise_hash = variables.get("ENTERPRISE_HASH")
    return odoo_hash, enterprise_hash
