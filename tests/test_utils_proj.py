# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from unittest import mock

import pytest

from odoo_tools.utils import proj as proj_utils
from odoo_tools.utils.config import config
from odoo_tools.utils.path import build_path

from .common import MockSubprocessRun, compare_line_by_line


@pytest.mark.project_setup(proj_tmpl_ver="2", proj_version="16.0.1.1.0")
def test_generate_odoo_config_file(project):
    odoo_src_path = build_path(config.odoo_src_rel_path)
    odoo_enterprise_path = str(odoo_src_path / "../enterprise")
    venv_dir = build_path(".venv")
    odoo_exec = venv_dir / "bin/odoo"
    addons_dir = build_path("odoo/addons")
    config_file = build_path("odoo.cfg")

    def create_config():
        config_file.write_text("db_name=testdb\n")

    mock_fn = MockSubprocessRun(
        [
            {
                "args": [
                    odoo_exec,
                    "--save",
                    "-c",
                    config_file,
                    "-d",
                    "testdb",
                    f"--addons-path={addons_dir}, {odoo_enterprise_path},{odoo_src_path}/addons,{odoo_src_path}/odoo/addons",
                    "--workers=0",
                    "--stop-after-init",
                ],
                "sim_call": create_config,
            },
        ]
    )
    with mock.patch("subprocess.run", mock_fn):
        proj_utils.generate_odoo_config_file(
            venv_dir, odoo_src_path, odoo_enterprise_path, database_name="testdb"
        )
    expected = "db_name=testdb\n\nrunning_env=dev\n"
    compare_line_by_line(config_file.read_text(), expected)
