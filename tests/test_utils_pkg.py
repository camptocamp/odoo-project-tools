# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import pytest
import os
from click.testing import CliRunner

from odoo_tools.utils import pkg as pkg_utils
from .common import mock_pypi_version_cache, make_fake_project_root


def test_pkg_class():
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "1.9.0")
    runner = CliRunner()
    with runner.isolated_filesystem():
        make_fake_project_root()
        pkg = pkg_utils.Package(addon_name)
    assert pkg.odoo
    assert pkg.name == addon_name
    assert pkg.pypi_name == f"odoo-addon-{addon_name}"
    assert pkg.latest_version == "1.9.0"
    assert pkg.pinned_version is None

