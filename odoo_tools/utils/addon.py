"""Odoo Addon utilities"""

import ast
from os import PathLike
from pathlib import Path


def get_manifest_path(addon_path: PathLike) -> Path:
    return Path(addon_path) / "__manifest__.py"


def read_manifest(addon_or_manifest_path: PathLike) -> dict[str, str]:
    addon_or_manifest_path = Path(addon_or_manifest_path)
    if addon_or_manifest_path.is_file():
        manifest_path = addon_or_manifest_path
        assert manifest_path.name == "__manifest__.py"
    elif addon_or_manifest_path.is_dir():
        manifest_path = get_manifest_path(addon_or_manifest_path)
    else:
        raise FileNotFoundError(addon_or_manifest_path)
    return ast.literal_eval(manifest_path.read_text())


def get_version(addon_path: PathLike) -> str:
    version = read_manifest(addon_path).get("version")
    if version is None:
        raise ValueError(f"Manifest file {addon_path} does not contain a version")
    return version
