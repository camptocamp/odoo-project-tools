# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import configparser
import shutil

PKG_NAME = "odoo_tools"
try:
    from importlib.resources import files
except ImportError:
    # py < 3.9
    from importlib_resources import files


def get_file_path(filepath):
    return files(PKG_NAME) / filepath


def get_template_path(filepath):
    return get_file_path("templates/" + filepath)


def copy_file(src_path, dest_path):
    shutil.copy(src_path, dest_path)


class SmartDict(dict):
    """Dotted notation dict."""

    def __getattr__(self, attrib):
        val = self.get(attrib)
        return self.__class__(val) if type(val) is dict else val


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
