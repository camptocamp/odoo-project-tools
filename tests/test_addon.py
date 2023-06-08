# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo_tools import addon

from .common import fake_project_root, mock_pypi_version_cache


def test_add_new():
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "1.9.0")
    with fake_project_root() as runner:
        result = runner.invoke(addon.add, addon_name)
        with open("./requirements.txt") as fd:
            assert "odoo-addon-edi_oca == 1.9.0" in fd.read()
        assert result.exit_code == 0


def test_add_new_with_version():
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "1.9.0")
    with fake_project_root() as runner:
        version = "1.8.0"
        result = runner.invoke(addon.add, [addon_name, f"--version={version}"])
        with open("./requirements.txt") as fd:
            assert f"odoo-addon-edi_oca == {version}" in fd.read()
        assert result.exit_code == 0


def test_upgrade():
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "2.0.0")
    with fake_project_root() as runner:
        with open("./requirements.txt", "w") as fd:
            fd.write("odoo-addon-edi_oca == 1.8.0")
        result = runner.invoke(addon.add, [addon_name, "--upgrade"], input="y")
        version = "2.0.0"
        with open("./requirements.txt") as fd:
            assert f"odoo-addon-edi_oca == {version}" in fd.read()
        assert result.exit_code == 0


def test_add_new_with_pr():
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "1.9.0")
    with fake_project_root() as runner:
        pr = "https://github.com/OCA/edi-framework/pull/3"
        expected = "odoo-addon-edi_oca @ git+https://github.com/OCA/edi-framework@refs/pull/3/head#subdirectory=setup/edi_oca"
        result = runner.invoke(addon.add, [addon_name, f"-p {pr}"])
        with open("./requirements.txt") as fd:
            assert expected in fd.read()
        assert result.exit_code == 0


def test_replace_pr():
    addon_name = "edi_oca"
    mock_pypi_version_cache(f"odoo-addon-{addon_name}", "2.0.0")
    old_req = "odoo-addon-edi_oca @ git+https://github.com/OCA/edi-framework@refs/pull/3/head#subdirectory=setup/edi_oca"
    with fake_project_root() as runner:
        with open("./requirements.txt", "w") as fd:
            fd.write(old_req)
        result = runner.invoke(addon.add, [addon_name])
        version = "2.0.0"
        with open("./requirements.txt") as fd:
            assert f"odoo-addon-edi_oca == {version}" in fd.read()
        assert result.exit_code == 0
