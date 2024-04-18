# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from unittest import mock

from odoo_tools.config import get_conf_key
from odoo_tools.utils import proj as proj_utils
from odoo_tools.utils.path import build_path

from .common import compare_line_by_line, fake_project_root, mock_subprocess_run


def test_get_project_manifest_1():
    with fake_project_root():
        manifest = proj_utils.get_project_manifest()
        expected = {
            "country": "ch",
            "customer_name": "ACME Inc.",
            "customer_shortname": "acme",
            "odoo_aux_langs": "fr_CH;it_IT",
            "odoo_company_name": "ACME Inc.",
            "odoo_main_lang": "de_DE",
            "odoo_version": "14.0",
            "platform_name": "azure",
            "project_id": "1234",
            "project_name": "acme_odoo",
            "repo_name": "acme_odoo",
        }
        for k, v in expected.items():
            assert manifest[k] == v


def test_get_project_manifest_2():
    with fake_project_root(manifest=dict(odoo_version="16.0", project_id="4321")):
        manifest = proj_utils.get_project_manifest()
        expected = {
            "country": "ch",
            "customer_name": "ACME Inc.",
            "customer_shortname": "acme",
            "odoo_aux_langs": "fr_CH;it_IT",
            "odoo_company_name": "ACME Inc.",
            "odoo_main_lang": "de_DE",
            "odoo_version": "16.0",
            "platform_name": "azure",
            "project_id": "4321",
            "project_name": "acme_odoo",
            "repo_name": "acme_odoo",
        }
        for k, v in expected.items():
            assert manifest[k] == v


def test_get_project_manifest_key():
    with fake_project_root():
        assert proj_utils.get_project_manifest_key("project_id") == "1234"
        assert proj_utils.get_project_manifest_key("customer_shortname") == "acme"


def test_generate_odoo_config_file():
    with fake_project_root(proj_tmpl_ver="2", proj_version="16.0.1.1.0"):
        odoo_src_path = build_path(get_conf_key("odoo_src_rel_path"))
        odoo_enterprise_path = str(odoo_src_path / "../enterprise")
        venv_dir = build_path(".venv")
        odoo_exec = venv_dir / "bin/odoo"
        addons_dir = build_path("odoo/addons")
        config_file = build_path("odoo.cfg")

        def create_config():
            with open(config_file, "w") as fobj:
                fobj.write("db_name=testdb\n")

        mock_fn = mock_subprocess_run(
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
        with open(config_file) as fobj:
            config = fobj.read()
        expected = "db_name=testdb\n\nrunning_env=dev\n"
        compare_line_by_line(config, expected)
