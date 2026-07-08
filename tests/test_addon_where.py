# Copyright 2024 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo_tools.cli import addon
from odoo_tools.utils.config import config

from .common import make_fake_addon


def test_where_found_in_local_src(project):
    make_fake_addon(config.local_src_rel_path / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    assert str(config.local_src_rel_path / "my_addon") in result.output


def test_where_found_in_ext_src(project):
    make_fake_addon(config.ext_src_rel_path / "some_repo" / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    assert str(config.ext_src_rel_path / "some_repo" / "my_addon") in result.output


def test_where_found_in_odoo_addons(project):
    make_fake_addon(config.odoo_src_rel_path / "addons" / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    assert str(config.odoo_src_rel_path / "addons" / "my_addon") in result.output


def test_where_found_in_odoo_base_addons(project):
    make_fake_addon(config.odoo_src_rel_path / "odoo" / "addons" / "my_addon")
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
    make_fake_addon(config.local_src_rel_path / "my_addon")
    make_fake_addon(config.odoo_src_rel_path / "addons" / "my_addon")
    result = project.invoke(addon.where, "my_addon")
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert len(lines) == 2
    assert str(config.local_src_rel_path / "my_addon") in lines[0]
    assert str(config.odoo_src_rel_path / "addons" / "my_addon") in lines[1]


def test_where_openerp_manifest(project):
    make_fake_addon(
        config.local_src_rel_path / "old_addon", manifest_filename="__openerp__.py"
    )
    result = project.invoke(addon.where, "old_addon")
    assert result.exit_code == 0
    assert str(config.local_src_rel_path / "old_addon") in result.output


def test_where_directory_without_manifest(project):
    path = config.local_src_rel_path / "not_an_addon"
    path.mkdir(parents=True, exist_ok=True)
    result = project.invoke(addon.where, "not_an_addon")
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
