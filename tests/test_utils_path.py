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
    os.chdir(nested_path)
    assert path_utils.root_path().as_posix() == str(curr_dir)
    os.chdir("/tmp")
    with pytest.raises(exceptions.ProjectRootFolderNotFound):
        path_utils.root_path()


def test_build_path(project):
    curr_dir = Path().resolve()
    (curr_dir / "sub").mkdir()
    (curr_dir / "sub/foo.baz").write_text("test")
    assert path_utils.build_path("nested/yo.txt") == curr_dir / "nested/yo.txt"
    assert (
        path_utils.build_path("another.file", from_file="sub/foo.baz")
        == curr_dir / "sub/another.file"
    )
