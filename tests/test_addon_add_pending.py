# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import pytest

from odoo_tools.cli import addon
from odoo_tools.utils.pending_merge import Repo
from odoo_tools.utils.pkg import Package
from odoo_tools.utils.req import get_project_dev_req

# TODO: test w/ aggregate


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"), proj_version="16.0.0.1.0"
)
def test_add_new_pending_no_addons(project):
    pr = "https://github.com/OCA/edi-framework/pull/1"
    repo_name = "edi-framework"
    repo = Repo(repo_name, path_check=False)
    assert not repo.has_pending_merges()
    result = project.invoke(
        addon.add_pending,
        [pr, "--no-aggregate"],
    )
    expected = [
        "No addon specifified. Please update dev requirements manually.",
    ]
    assert result.output.splitlines() == expected
    assert repo.has_pending_merges()


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"), proj_version="16.0.0.1.0"
)
def test_add_new_pending_with_addon_editable(project):
    pr = "https://github.com/OCA/edi-framework/pull/1"
    repo_name = "edi-framework"
    addon_name = "edi_oca"
    repo = Repo(repo_name, path_check=False)
    req_path = get_project_dev_req()
    assert not req_path.exists()
    pkg = Package(addon_name, req_filepath=req_path)
    assert not repo.has_pending_merges()
    result = project.invoke(addon.add_pending, [pr, "-a", addon_name, "--no-aggregate"])
    expected = [
        f"Adding: {addon_name} from https://github.com/OCA/edi-framework/pull/1",
        f"Updated dev requirements for: {addon_name}",
    ]
    assert result.output.splitlines() == expected
    assert req_path.exists()
    assert repo.has_pending_merges()
    assert pkg.is_editable()
    assert pkg.is_local()


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"), proj_version="16.0.0.1.0"
)
def test_add_new_pending_with_addon_not_editable(project):
    pr = "https://github.com/OCA/edi-framework/pull/1"
    repo_name = "edi-framework"
    addon_name = "edi_oca"
    repo = Repo(repo_name, path_check=False)
    req_path = get_project_dev_req()
    assert not req_path.exists()
    pkg = Package(addon_name, req_filepath=req_path)
    assert not repo.has_pending_merges()
    result = project.invoke(
        addon.add_pending, [pr, "-a", addon_name, "--no-editable", "--no-aggregate"]
    )
    expected = [
        f"Adding: {addon_name} from https://github.com/OCA/edi-framework/pull/1",
        f"Updated dev requirements for: {addon_name}",
    ]
    assert result.output.splitlines() == expected
    assert req_path.exists()
    assert repo.has_pending_merges()
    assert not pkg.is_editable()
    assert not pkg.is_local()
    assert pkg.has_pending_merge()
