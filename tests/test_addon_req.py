# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


import pytest

from odoo_tools.cli import addon
from odoo_tools.utils.path import root_path


@pytest.mark.project_setup(proj_version="16.0.1.0.0")
def test_add_base(project):
    addon_name = "edi_oca"
    result = project.invoke(addon.add_requirement, addon_name)
    assert result.output.splitlines() == [
        f"Requirement line for: {addon_name}",
        "",
        "odoo-addon-edi_oca",
        "",
    ]
    result = project.invoke(addon.add_requirement, [addon_name, "-v", "16.0.1.2.0"])
    assert result.output.splitlines() == [
        f"Requirement line for: {addon_name}",
        "",
        "odoo-addon-edi_oca == 16.0.1.2.0",
        "",
    ]
    assert result.exit_code == 0


@pytest.mark.project_setup(proj_version="16.0.1.0.0")
def test_add_pr(project):
    addon_name = "edi_oca"
    result = project.invoke(
        addon.add_requirement,
        [addon_name, "-p", "https://github.com/OCA/edi/pull/778"],
    )
    assert result.output.splitlines() == [
        f"Requirement line for: {addon_name}",
        "",
        "odoo-addon-edi_oca @ git+https://github.com/OCA/edi@refs/pull/778/head#subdirectory=setup/edi_oca",
        "",
    ]
    assert result.exit_code == 0


@pytest.mark.project_setup(proj_version="16.0.3.0.0")
def test_add_pr_to_file_16(project):
    req_path = "tmp-requirements.txt"
    path = root_path() / req_path
    result = project.invoke(
        addon.add_requirement,
        [
            "edi_oca",
            "-p",
            "https://github.com/OCA/edi/pull/778",
            "-f",
            req_path,
            "-v",
            "16",
        ],
    )
    with path.open() as fd:
        content = fd.read()
        assert (
            content
            == "odoo-addon-edi_oca @ git+https://github.com/OCA/edi@refs/pull/778/head#subdirectory=setup/edi_oca"
        )
    assert result.exit_code == 0


@pytest.mark.project_setup(proj_version="18.0.1.0.0")
def test_add_pr_to_file_18(project):
    req_path = "tmp-requirements.txt"
    path = root_path() / req_path
    result = project.invoke(
        addon.add_requirement,
        ["edi_oca", "-p", "https://github.com/OCA/edi/pull/778", "-f", req_path],
    )
    with path.open() as fd:
        content = fd.read()
        assert (
            content
            == "odoo-addon-edi_oca @ git+https://github.com/OCA/edi@refs/pull/778/head#subdirectory=edi_oca"
        )
    assert result.exit_code == 0


@pytest.mark.project_setup(proj_version="16.0.1.0.0")
def test_add_fork(project):
    addon_name = "edi_oca"
    result = project.invoke(
        addon.add_requirement, [addon_name, "-b", "mybranch", "-r", "edi"]
    )
    # Not sure why the output is messed up when using result.output, but is ok.
    assert (
        result.stdout
        == "Requirement line for: edi_oca\n\nodoo-addon-edi_oca @ git+https://github.com/camptocamp/edi@mybranch#subdirectory=setup/edi_oca\n\n"
    )
    assert result.exit_code == 0
