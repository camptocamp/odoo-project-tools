# Copyright 2024 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from pathlib import Path

from odoo_tools.cli import addon
from odoo_tools.utils.config import config


def _make_addon(path, manifest="__manifest__.py"):
    """Create a minimal addon directory with a manifest file."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / manifest).write_text("{}")


def test_where_found_in_local_src(project):
    _make_addon(config.local_src_rel_path / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    assert str(config.local_src_rel_path / "my_addon") in result.output


def test_where_found_in_ext_src(project):
    _make_addon(config.ext_src_rel_path / "some_repo" / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    assert str(config.ext_src_rel_path / "some_repo" / "my_addon") in result.output


def test_where_found_in_odoo_addons(project):
    _make_addon(config.odoo_src_rel_path / "addons" / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    assert str(config.odoo_src_rel_path / "addons" / "my_addon") in result.output


def test_where_found_in_odoo_base_addons(project):
    _make_addon(config.odoo_src_rel_path / "odoo" / "addons" / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    assert (
        str(config.odoo_src_rel_path / "odoo" / "addons" / "my_addon") in result.output
    )


def test_where_not_found(project):
    result = project.invoke(addon.where, "nonexistent_addon")
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_where_multiple_occurrences(project):
    _make_addon(config.local_src_rel_path / "my_addon")
    _make_addon(config.odoo_src_rel_path / "addons" / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert len(lines) == 2
    assert str(config.local_src_rel_path / "my_addon") in lines[0]
    assert str(config.odoo_src_rel_path / "addons" / "my_addon") in lines[1]


def test_where_openerp_manifest(project):
    _make_addon(config.local_src_rel_path / "old_addon", manifest="__openerp__.py")
    result = project.invoke(addon.where, "old_addon")
    assert result.exit_code == 0
    assert str(config.local_src_rel_path / "old_addon") in result.output


def test_where_directory_without_manifest(project):
    path = config.local_src_rel_path / "not_an_addon"
    path.mkdir(parents=True, exist_ok=True)
    result = project.invoke(addon.where, "not_an_addon")
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
