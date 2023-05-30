# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

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
