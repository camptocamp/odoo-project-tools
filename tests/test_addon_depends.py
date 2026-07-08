# Copyright 2026 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import pytest

from odoo_tools.cli import addon
from odoo_tools.utils.config import config

from .common import make_fake_addon


@pytest.fixture()
def project_addons(project):
    """A fake project with a small addon dependency tree."""
    make_fake_addon(config.odoo_src_rel_path / "odoo" / "addons" / "base")
    make_fake_addon(
        config.ext_src_rel_path / "some_repo" / "oca_base_addon", depends=["base"]
    )
    make_fake_addon(
        config.ext_src_rel_path / "some_repo" / "oca_addon",
        depends=["oca_base_addon", "base"],
    )
    make_fake_addon(
        config.local_src_rel_path / "my_addon", depends=["oca_addon", "base"]
    )
    make_fake_addon(config.local_src_rel_path / "other_addon", depends=["my_addon"])
    return project


def test_list(project_addons):
    result = project_addons.invoke(addon.list_addons)
    assert result.exit_code == 0
    assert result.output.splitlines() == ["my_addon", "other_addon"]


def test_list_separator(project_addons):
    result = project_addons.invoke(addon.list_addons, "--separator ,")
    assert result.exit_code == 0
    assert result.output.splitlines() == ["my_addon,other_addon"]


def test_list_excludes_not_installable(project_addons):
    make_fake_addon(config.local_src_rel_path / "wip_addon", installable=False)
    result = project_addons.invoke(addon.list_addons)
    assert result.exit_code == 0
    assert "wip_addon" not in result.output


def test_depends_direct(project_addons):
    result = project_addons.invoke(addon.depends, "my_addon")
    assert result.exit_code == 0
    assert result.output.splitlines() == ["base", "oca_addon"]


def test_depends_transitive(project_addons):
    result = project_addons.invoke(addon.depends, "my_addon --transitive")
    assert result.exit_code == 0
    assert result.output.splitlines() == ["base", "oca_addon", "oca_base_addon"]


def test_depends_include_selected(project_addons):
    result = project_addons.invoke(addon.depends, "my_addon --include-selected")
    assert result.exit_code == 0
    assert result.output.splitlines() == ["base", "my_addon", "oca_addon"]


def test_depends_multiple_addons(project_addons):
    result = project_addons.invoke(addon.depends, "my_addon other_addon")
    assert result.exit_code == 0
    assert result.output.splitlines() == ["base", "oca_addon"]


def test_depends_comma_separated(project_addons):
    result = project_addons.invoke(addon.depends, "my_addon,other_addon")
    assert result.exit_code == 0
    assert result.output.splitlines() == ["base", "oca_addon"]


def test_depends_no_addons_selects_local_src(project_addons):
    result = project_addons.invoke(addon.depends)
    assert result.exit_code == 0
    assert result.output.splitlines() == ["base", "oca_addon"]


def test_depends_no_addons_transitive_include_selected(project_addons):
    """List all the addons used by the project."""
    result = project_addons.invoke(addon.depends, "--transitive --include-selected")
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "base",
        "my_addon",
        "oca_addon",
        "oca_base_addon",
        "other_addon",
    ]


def test_depends_unknown_addon(project_addons):
    result = project_addons.invoke(addon.depends, "nonexistent_addon")
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_depends_fails_on_missing_dependencies(project_addons):
    make_fake_addon(config.local_src_rel_path / "broken_addon", depends=["ghost"])
    result = project_addons.invoke(addon.depends, "broken_addon --transitive")
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    assert "ghost" in result.output


def test_depends_ignore_missing_warns_about_missing_dependencies(project_addons):
    make_fake_addon(config.local_src_rel_path / "broken_addon", depends=["ghost"])
    result = project_addons.invoke(
        addon.depends, "broken_addon --transitive --ignore-missing"
    )
    assert result.exit_code == 0
    assert result.stdout.splitlines() == ["ghost"]
    assert "not found" in result.stderr
    assert "ghost" in result.stderr


def test_depends_quiet_hides_missing_addons_warning(project_addons):
    make_fake_addon(config.local_src_rel_path / "broken_addon", depends=["ghost"])
    result = project_addons.invoke(
        addon.depends, "broken_addon --transitive --ignore-missing --quiet"
    )
    assert result.exit_code == 0
    assert result.stdout.splitlines() == ["ghost"]
    assert result.stderr == ""


def test_depends_separator(project_addons):
    result = project_addons.invoke(addon.depends, "my_addon --separator ,")
    assert result.exit_code == 0
    assert result.output.splitlines() == ["base,oca_addon"]


def test_codepends_default(project_addons):
    result = project_addons.invoke(addon.codepends, "oca_base_addon")
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "my_addon",
        "oca_addon",
        "oca_base_addon",
        "other_addon",
    ]


def test_codepends_no_transitive(project_addons):
    result = project_addons.invoke(addon.codepends, "oca_base_addon --no-transitive")
    assert result.exit_code == 0
    assert result.output.splitlines() == ["oca_addon", "oca_base_addon"]


def test_codepends_no_include_selected(project_addons):
    result = project_addons.invoke(
        addon.codepends, "oca_base_addon --no-include-selected"
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == ["my_addon", "oca_addon", "other_addon"]


def test_codepends_multiple_addons(project_addons):
    result = project_addons.invoke(
        addon.codepends, "oca_addon,base --no-transitive --no-include-selected"
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == ["my_addon", "oca_base_addon"]


def test_codepends_unknown_addon(project_addons):
    result = project_addons.invoke(addon.codepends, "nonexistent_addon")
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_codepends_ignore_missing_warns_about_unknown_addon(project_addons):
    result = project_addons.invoke(
        addon.codepends, "nonexistent_addon --ignore-missing --no-include-selected"
    )
    assert result.exit_code == 0
    assert result.stdout.splitlines() == []
    assert "not found" in result.stderr
    assert "nonexistent_addon" in result.stderr


def test_codepends_quiet_hides_missing_addons_warning(project_addons):
    result = project_addons.invoke(
        addon.codepends,
        "nonexistent_addon --ignore-missing --no-include-selected --quiet",
    )
    assert result.exit_code == 0
    assert result.stdout.splitlines() == []
    assert result.stderr == ""


def test_codepends_separator(project_addons):
    result = project_addons.invoke(addon.codepends, "oca_base_addon --separator ,")
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "my_addon,oca_addon,oca_base_addon,other_addon"
    ]
