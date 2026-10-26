# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path

import pytest

from odoo_tools.cli import addon
from odoo_tools.exceptions import ProjectConfigException, ProjectRootFolderNotFound
from odoo_tools.utils.config import ProjectConfig, config, load_config

from .common import make_fake_addon


def test_load_config_without_proj_cfg(project):
    Path(".proj.cfg").unlink()
    assert load_config(Path(".proj.cfg")) == ProjectConfig(
        template_version=1,
        company_git_remote="camptocamp",
        odoo_src_rel_path=Path("odoo/src"),
        ext_src_rel_path=Path("odoo/external-src"),
        local_src_rel_path=Path("odoo/local-src"),
        pending_merge_rel_path=Path("pending-merges.d"),
        version_file_rel_path=None,
        marabunta_mig_file_rel_path=None,
        otools_min_version=None,
    )


def test_load_config_partial_proj_cfg(project):
    Path(".proj.cfg").write_text("[conf]\nlocal_src_rel_path = odoo/addons\n")
    loaded = load_config(Path(".proj.cfg"))
    assert loaded.local_src_rel_path == Path("odoo/addons")
    assert loaded.odoo_src_rel_path == Path("odoo/src")
    assert loaded.company_git_remote == "camptocamp"


def test_load_config_malformed_proj_cfg(project):
    Path(".proj.cfg").write_text("[conf]\notools_min_version = not-a-version\n")
    with pytest.raises(ProjectConfigException, match="otools_min_version"):
        load_config(Path(".proj.cfg"))


def test_load_config_outside_project_root(runner):
    with pytest.raises(ProjectRootFolderNotFound):
        load_config(Path(".proj.cfg"))


def test_addon_where_without_proj_cfg(project):
    Path(".proj.cfg").unlink()
    config._reload()
    make_fake_addon(Path("odoo/local-src/my_addon"))
    result = project.invoke(addon.where, "my_addon", catch_exceptions=False)
    assert result.exit_code == 0
    assert "odoo/local-src/my_addon" in result.output
