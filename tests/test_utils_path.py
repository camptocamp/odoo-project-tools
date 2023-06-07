# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

import pytest
from click.testing import CliRunner

from odoo_tools import exceptions
from odoo_tools.utils import path as path_utils

from .common import make_fake_project_root


def test_root_path():
    runner = CliRunner()
    with runner.isolated_filesystem():
        curr_dir = os.getcwd()
        nested_path = "nested/project/path"
        os.makedirs(nested_path, exist_ok=True)
        assert os.path.exists(f"./{nested_path}")
        make_fake_project_root()
        assert path_utils.root_path().as_posix() == curr_dir
        os.chdir(nested_path)
        assert path_utils.root_path().as_posix() == curr_dir
        os.chdir("/tmp")
        with pytest.raises(exceptions.ProjectRootFolderNotFound):
            path_utils.root_path()
