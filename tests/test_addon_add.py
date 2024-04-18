# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import pytest

from odoo_tools.cli import addon

from .common import mock_pypi_version_cache


def test_add_new(project):
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo13-addon-{addon_name}", "13.0.1.9.0")
    mock_pypi_version_cache(f"odoo14-addon-{addon_name}", "14.0.1.9.0")
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "15.0.1.9.0")
    result = project.invoke(addon.add, addon_name)
    with open("./requirements.txt") as fd:
        assert "odoo14-addon-edi_oca == 14.0.1.9.0" in fd.read()
    assert result.exit_code == 0


def test_add_new_with_version(project):
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo13-addon-{addon_name}", "13.0.1.9.0")
    mock_pypi_version_cache(f"odoo14-addon-{addon_name}", "14.0.1.9.0")
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "15.0.1.9.0")
    version = "14.0.1.8.0"
    result = project.invoke(addon.add, [addon_name, f"--version={version}"])
    with open("./requirements.txt") as fd:
        assert f"odoo14-addon-edi_oca == {version}" in fd.read()
    assert result.exit_code == 0


def test_upgrade(project):
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo14-addon-{addon_name}", "14.0.2.0.0")
    with open("./requirements.txt", "w") as fd:
        fd.write("odoo14-addon-edi_oca == 14.0.1.8.0")
    result = project.invoke(addon.add, [addon_name, "--upgrade"], input="y")
    version = "14.0.2.0.0"
    with open("./requirements.txt") as fd:
        assert f"odoo14-addon-edi_oca == {version}" in fd.read()
    assert result.exit_code == 0


@pytest.mark.project_setup(
    proj_version="16.0.0.1.0", manifest=dict(odoo_version="16.0")
)
def test_add_new_with_pr(project):
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "16.0.1.9.0")
    pr = "https://github.com/OCA/edi-framework/pull/3"
    expected = "odoo-addon-edi_oca @ git+https://github.com/OCA/edi-framework@refs/pull/3/head#subdirectory=setup/edi_oca"
    result = project.invoke(addon.add, [addon_name, f"-p {pr}"])
    with open("./requirements.txt") as fd:
        assert expected in fd.read()
    assert result.exit_code == 0


@pytest.mark.project_setup(
    proj_version="16.0.0.1.0", manifest=dict(odoo_version="16.0")
)
def test_replace_pr(project):
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "16.0.2.0.0")
    old_req = "odoo-addon-edi_oca @ git+https://github.com/OCA/edi-framework@refs/pull/3/head#subdirectory=setup/edi_oca"
    with open("./requirements.txt", "w") as fd:
        fd.write(old_req)
    result = project.invoke(addon.add, [addon_name])
    version = "16.0.2.0.0"
    with open("./requirements.txt") as fd:
        assert f"odoo-addon-edi_oca == {version}" in fd.read()
    assert result.exit_code == 0
