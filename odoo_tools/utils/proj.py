# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from functools import lru_cache

from .path import get_root_marker, root_path
from .yaml import yaml_load


@lru_cache(maxsize=None)
def get_project_manifest(key=None):
    path = root_path() / get_root_marker()
    with open(path) as f:
        return yaml_load(f.read())


def get_project_manifest_key(key):
    return get_project_manifest()[key]
