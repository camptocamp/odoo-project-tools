# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from pathlib import Path

import pytest

from odoo_tools import exceptions
from odoo_tools.utils import path as path_utils

from .common import make_fake_project_root


def test_root_path(runner):
    curr_dir = Path().resolve()
    nested_path = "nested/project/path"
    (curr_dir / nested_path).mkdir(parents=True, exist_ok=True)
    assert (Path() / nested_path).exists()
    make_fake_project_root()
    assert path_utils.root_path().as_posix() == str(curr_dir)
    # From within the tree (e.g. a submodule), git still resolves the root.
    os.chdir(nested_path)
    path_utils.root_path.cache_clear()
    assert path_utils.root_path().as_posix() == str(curr_dir)
    # Outside any git repository, root discovery fails loudly.
    os.chdir("/tmp")
    path_utils.root_path.cache_clear()
    with pytest.raises(exceptions.ProjectRootFolderNotFound):
        path_utils.root_path()


def test_build_path(project):
    curr_dir = Path().resolve()
    assert path_utils.build_path("nested/yo.txt") == curr_dir / "nested/yo.txt"
