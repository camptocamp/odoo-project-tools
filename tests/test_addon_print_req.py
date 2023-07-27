# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo_tools.cli import addon

from .common import fake_project_root


def test_print_base():
    addon_name = "edi_oca"
    with fake_project_root(proj_version="16.0.1.0.0") as runner:
        result = runner.invoke(addon.print_requirement, addon_name)
        assert result.output.splitlines() == [
            f"Requirement line for: {addon_name}",
            "",
            "odoo-addon-edi_oca",
            "",
        ]
        result = runner.invoke(
            addon.print_requirement, [addon_name, "-v", "16.0.1.2.0"]
        )
        assert result.output.splitlines() == [
            f"Requirement line for: {addon_name}",
            "",
            "odoo-addon-edi_oca == 16.0.1.2.0",
            "",
        ]
        assert result.exit_code == 0


def test_print_pr():
    addon_name = "edi_oca"
    with fake_project_root(proj_version="16.0.1.0.0") as runner:
        result = runner.invoke(
            addon.print_requirement,
            [addon_name, "-p", "https://github.com/OCA/edi/pull/778"],
        )
        assert result.output.splitlines() == [
            f"Requirement line for: {addon_name}",
            "",
            "odoo-addon-edi_oca @ git+https://github.com/OCA/edi@refs/pull/778/head#subdirectory=setup/edi_oca",
            "",
        ]
        assert result.exit_code == 0


def test_print_fork():
    addon_name = "edi_oca"
    with fake_project_root(proj_version="16.0.1.0.0") as runner:
        result = runner.invoke(
            addon.print_requirement, [addon_name, "-b", "mybranch", "-r", "edi"]
        )
        # Not sure why the output is messed up when using result.output, but is ok.
        assert (
            result.stdout
            == "Requirement line for: edi_oca\n\nodoo-addon-edi_oca @ git+https://github.com/camptocamp/edi@mybranch#subdirectory=setup/edi_oca\n\n"
        )
        assert result.exit_code == 0
