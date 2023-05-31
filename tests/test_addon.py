# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

from click.testing import CliRunner
from odoo_tools import addon
from .common import mock_pypi_version_cache
from .common import make_fake_project_root


def test_add_new():
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "1.9.0")
    runner = CliRunner()
    with runner.isolated_filesystem():
        make_fake_project_root()
        result = runner.invoke(addon.add, addon_name)
        with open("requirements.txt") as fd:
            assert "odoo-addon-edi_oca == 1.9.0" in list(fd.readlines())


def test_add_new_pr():
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "1.9.0")
    runner = CliRunner()
    with runner.isolated_filesystem():
        make_fake_project_root()
        mod_name = "edi_record_metadata_oca"
        pr = "https://github.com/OCA/edi-framework/pull/3"
        result = runner.invoke(addon.add, addon_name, pr=pr)
        with open("requirements.txt") as fd:
            assert "odoo-addon-edi_oca == 1.9.0" in list(fd.readlines())