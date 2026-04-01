# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path

from odoo_tools.utils import pkg as pkg_utils

from .common import mock_pypi_version_cache


def test_pkg_class(project):
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo14-addon-{addon_name}", "14.0.1.9.0")
    pkg = pkg_utils.Package(addon_name)
    assert pkg.odoo
    assert pkg.name == addon_name
    assert pkg.pypi_name == f"odoo14-addon-{addon_name}"
    assert pkg.latest_version == "14.0.1.9.0"
    assert pkg.pinned_version is None


def test_pkg_class_has_pending_merge(project):
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo14-addon-{addon_name}", "14.0.1.9.0")
    pkg = pkg_utils.Package(addon_name)
    old_req = f"{pkg.pypi_name} @ git+https://github.com/OCA/repo@refs/pull/3/head#subdirectory=setup/{pkg.name}"
    (Path() / "requirements.txt").write_text(old_req)
    req_path = Path().resolve() / "requirements.txt"
    pkg = pkg_utils.Package(addon_name, req_filepath=req_path)
    assert pkg.has_pending_merge()


def test_pkg_class_is_editable(project):
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo14-addon-{addon_name}", "14.0.1.9.0")
    pkg = pkg_utils.Package(addon_name)
    old_req = f"-e path/to/module/setup/{addon_name}"
    (Path() / "requirements.txt").write_text(old_req)
    req_path = Path().resolve() / "requirements.txt"
    pkg = pkg_utils.Package(addon_name, req_filepath=req_path)
    assert pkg.is_editable()
