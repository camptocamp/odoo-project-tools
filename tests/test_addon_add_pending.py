# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import os

from odoo_tools.cli import addon
from odoo_tools.utils.pending_merge import Repo
from odoo_tools.utils.pkg import Package

from .common import fake_project_root
from .fixtures import clear_caches  # noqa


def test_add_new_pending_no_addons():
    pr = "https://github.com/OCA/edi-framework/pull/1"
    repo_name = "edi-framework"
    with fake_project_root(manifest=dict(odoo_version="16.0")) as runner:
        repo = Repo(repo_name, path_check=False)
        assert not repo.has_pending_merges()
        result = runner.invoke(
            addon.add_pending,
            [
                pr,
            ],
        )
        expected = [
            "Adding: https://github.com/OCA/edi-framework/pull/1",
            "No addon specifified. Please update dev requirements manually.",
        ]
        assert result.output.splitlines() == expected
        assert repo.has_pending_merges()


def test_add_new_pending_with_addon_editable():
    pr = "https://github.com/OCA/edi-framework/pull/1"
    repo_name = "edi-framework"
    addon_name = "edi_oca"
    with fake_project_root(manifest=dict(odoo_version="16.0")) as runner:
        repo = Repo(repo_name, path_check=False)
        pkg = Package(addon_name)
        assert not repo.has_pending_merges()
        assert not pkg.is_editable()
        assert not pkg.is_local()
        assert not os.path.exists(os.getcwd() + "/dev-requirements.txt")
        result = runner.invoke(addon.add_pending, [pr, "-a", addon_name])
        expected = [
            "Adding: https://github.com/OCA/edi-framework/pull/1",
            f"Updated dev requirements for: {addon_name}",
        ]
        assert result.output.splitlines() == expected
        assert os.path.exists(os.getcwd() + "/dev-requirements.txt")
        assert repo.has_pending_merges()
        assert pkg.is_editable()
        assert pkg.is_local()


def test_add_new_pending_with_addon_not_editable():
    pr = "https://github.com/OCA/edi-framework/pull/1"
    repo_name = "edi-framework"
    addon_name = "edi_oca"
    with fake_project_root(manifest=dict(odoo_version="16.0")) as runner:
        repo = Repo(repo_name, path_check=False)
        pkg = Package(addon_name)
        assert not repo.has_pending_merges()
        assert not pkg.has_pending_merge()
        assert not pkg.is_editable()
        assert not pkg.is_local()
        assert not os.path.exists(os.getcwd() + "/dev-requirements.txt")
        result = runner.invoke(
            addon.add_pending, [pr, "-a", addon_name, "--no-editable"]
        )
        expected = [
            "Adding: https://github.com/OCA/edi-framework/pull/1",
            f"Updated dev requirements for: {addon_name}",
        ]
        assert result.output.splitlines() == expected
        assert os.path.exists(os.getcwd() + "/dev-requirements.txt")
        assert repo.has_pending_merges()
        assert not pkg.is_editable()
        assert not pkg.is_local()
        assert pkg.has_pending_merge()
