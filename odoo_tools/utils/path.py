# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from contextlib import contextmanager
from pathlib import PosixPath

from ..exceptions import ProjectRootFolderNotFound
from . import ui


def get_root_marker():
    return ".cookiecutter.context.yml"


# TODO: consider using `git rev-parse --show-superproject-working-tree / --show-toplevel`
# to find out the root of the project w/o relying on marker files.


def root_path(marker_file=get_root_marker(), raise_if_missing=True):
    current_dir = (
        os.getcwd()
    )  # directory from where search for .cookiecutter.context.yml starts
    max_depth = 5
    while max_depth > 0:
        file_list = os.listdir(current_dir)
        parent_dir = os.path.dirname(current_dir)
        if marker_file in file_list:
            return PosixPath(current_dir)
        elif current_dir == parent_dir:
            break
        else:
            current_dir = parent_dir
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
        base_path = PosixPath(from_file).parent.resolve()
    return base_path / path


@contextmanager
def cd(path):
    prev = os.getcwd()
    os.chdir(os.path.expanduser(path))
    try:
        yield
    finally:
        os.chdir(prev)


def make_dir(path_dir):
    try:
        os.makedirs(path_dir)
    except OSError:
        if not os.path.isdir(path_dir):
            msg = f"Directory does not exist and could not be created: {path_dir}"
            ui.exit_msg(msg)
        else:
            pass  # directory already exists, nothing to do in this case
