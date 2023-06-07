# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

from ..exceptions import ProjectRootFolderNotFound


def get_root_marker():
    return ".cookiecutter.context.yml"


def root_path(marker_file=get_root_marker(), raise_if_missing=True):
    current_dir = (
        os.getcwd()
    )  # directory from where search for .cookiecutter.context.yml starts
    max_depth = 5
    while max_depth > 0:
        file_list = os.listdir(current_dir)
        parent_dir = os.path.dirname(current_dir)
        if marker_file in file_list:
            return current_dir
        else:
            if current_dir == parent_dir:
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
        base_path = os.path.dirname(os.path.realpath(from_file))

    return os.path.join(base_path, path)
