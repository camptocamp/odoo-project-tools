# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from contextlib import contextmanager
from pathlib import Path

from ..exceptions import ProjectRootFolderNotFound
from . import ui


def get_root_marker():
    return ".cookiecutter.context.yml"


# TODO: consider using `git rev-parse --show-superproject-working-tree / --show-toplevel`
# to find out the root of the project w/o relying on marker files.


def root_path(marker_file=None, raise_if_missing=True):
    if marker_file is None:
        marker_file = get_root_marker()
    # directory from where search for .cookiecutter.context.yml starts
    current_dir = Path.cwd()
    max_depth = 5
    while max_depth > 0:
        marker = current_dir / marker_file
        if marker.exists():
            return current_dir
        if current_dir.parent == current_dir:
            break
        current_dir = current_dir.parent
        max_depth -= 1
    if raise_if_missing:
        raise ProjectRootFolderNotFound(
            f"Missing {marker_file}. It's not a project directory. Exiting"
        )


# TODO: add test
def build_path(path, from_root=True, from_file=None):
    if not from_file and from_root:
        base_path = root_path()
    else:
        if from_file is None:
            from_file = __file__
        base_path = Path(from_file).parent.resolve()
    return base_path / path


@contextmanager
def cd(path):
    prev = Path.cwd()
    os.chdir(Path(path).expanduser())
    try:
        yield
    finally:
        os.chdir(prev)


def make_dir(path_dir):
    path_dir = Path(path_dir)
    try:
        path_dir.mkdir(parents=True)
    except OSError:
        if not path_dir.is_dir():
            msg = f"Directory does not exist and could not be created: {path_dir}"
            ui.exit_msg(msg)
        else:
            pass  # directory already exists, nothing to do in this case


def is_odoo_module(path: Path) -> bool:
    """Check if a path is a valid Odoo module."""
    return path.is_dir() and (path / "__manifest__.py").exists()
