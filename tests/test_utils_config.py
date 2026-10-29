# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path
from textwrap import dedent

import pytest

from odoo_tools.cli import addon
from odoo_tools.exceptions import ProjectConfigException, ProjectRootFolderNotFound
from odoo_tools.utils.config import (
    DEPRECATED_MANIFEST_PATH,
    config,
    load_config,
    migrate_config,
    read_pyproject_section,
    warn_deprecated_config_source,
)

from .common import make_fake_addon


@pytest.mark.project_setup(manifest=dict(odoo_version="18.0", project_id="4321"))
def test_config_from_pyproject(project):
    # Tool settings (formerly .proj.cfg) resolve from [tool.odoo-project]
    assert config.company_git_remote == "camptocamp"
    assert config.odoo_src_rel_path == Path("odoo/src")
    # Manifest values (formerly .cookiecutter.context.yml) resolve from it too
    assert config.odoo_version == "18.0"
    assert config.odoo_serie == 18
    assert config.project_id == "4321"
    assert config.customer_shortname == "acme"
    # The legacy files are not present
    assert not Path(".proj.cfg").exists()
    assert not Path(DEPRECATED_MANIFEST_PATH).exists()


def test_pyproject_emits_no_deprecation_warning(project, capsys):
    warn_deprecated_config_source.cache_clear()
    capsys.readouterr()  # drop anything emitted during setup
    config._reload()
    assert config.company_git_remote  # trigger config load
    assert "deprecated" not in capsys.readouterr().err


@pytest.mark.project_setup(legacy=True)
def test_legacy_files_merged_with_deprecation_warning(project, capsys):
    warn_deprecated_config_source.cache_clear()
    capsys.readouterr()  # drop anything emitted during setup
    config._reload()
    # Tool settings come from .proj.cfg, manifest values from the cookiecutter
    # file; both are merged into a single config.
    assert config.company_git_remote == "camptocamp"  # .proj.cfg
    assert config.customer_shortname == "acme"  # .cookiecutter.context.yml
    err = capsys.readouterr().err
    assert "deprecated" in err
    assert "[tool.odoo-project]" in err


@pytest.mark.project_setup(legacy=True)
def test_legacy_without_proj_cfg_uses_default_settings(project):
    Path(".proj.cfg").unlink()
    loaded = load_config()
    assert loaded.template_version == 1
    assert loaded.company_git_remote == "camptocamp"
    assert loaded.odoo_src_rel_path == Path("odoo/src")
    assert loaded.ext_src_rel_path == Path("odoo/external-src")
    assert loaded.local_src_rel_path == Path("odoo/local-src")
    assert loaded.pending_merge_rel_path == Path("pending-merges.d")
    assert loaded.version_file_rel_path is None
    assert loaded.marabunta_mig_file_rel_path is None
    assert loaded.otools_min_version is None
    # The manifest values still come from the cookiecutter file
    assert loaded.customer_shortname == "acme"


@pytest.mark.project_setup(legacy=True)
def test_legacy_partial_proj_cfg(project):
    Path(".proj.cfg").write_text("[conf]\nlocal_src_rel_path = odoo/addons\n")
    loaded = load_config()
    assert loaded.local_src_rel_path == Path("odoo/addons")
    assert loaded.odoo_src_rel_path == Path("odoo/src")
    assert loaded.company_git_remote == "camptocamp"


@pytest.mark.project_setup(legacy=True)
def test_legacy_malformed_proj_cfg(project):
    Path(".proj.cfg").write_text("[conf]\notools_min_version = not-a-version\n")
    with pytest.raises(ProjectConfigException, match="otools_min_version"):
        load_config()


def test_load_config_outside_project_root(runner):
    with pytest.raises(ProjectRootFolderNotFound):
        load_config()


@pytest.mark.project_setup(legacy=True)
def test_addon_where_without_proj_cfg(project):
    Path(".proj.cfg").unlink()
    config._reload()
    make_fake_addon(Path("odoo/local-src/my_addon"))
    result = project.invoke(addon.where, "my_addon", catch_exceptions=False)
    assert result.exit_code == 0
    assert "odoo/local-src/my_addon" in result.output


def test_missing_section_and_legacy_fails_loudly(project):
    # pyproject.toml present but without a [tool.odoo-project] section, and no
    # legacy files -> fail loudly about the missing section.
    Path("pyproject.toml").write_text("[project]\nname = 'acme'\n")
    config._reload()
    with pytest.raises(ProjectConfigException, match="tool.odoo-project"):
        _ = config.company_git_remote


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            company_git_remote = "sec-remote"
            odoo_version = "18.0"
            """
        ),
        ".proj.cfg": dedent(
            """\
            [conf]
            company_git_remote = cfg-remote
            local_src_rel_path = cfg/local-src
            """
        ),
        ".cookiecutter.context.yml": dedent(
            """\
            odoo_version: '16.0'
            customer_shortname: acme
            """
        ),
    }
)
def test_sources_layered_field_by_field(project):
    """[tool.odoo-project] wins over the legacy files, which win over the
    defaults, field by field: no source has to declare everything."""
    loaded = load_config()
    # Set everywhere: the section wins
    assert loaded.company_git_remote == "sec-remote"
    assert loaded.odoo_version == "18.0"
    # Only set in the legacy files: they fill the gaps
    assert loaded.local_src_rel_path == Path("cfg/local-src")
    assert loaded.customer_shortname == "acme"
    # Set nowhere: the default
    assert loaded.ext_src_rel_path == Path("odoo/external-src")
    assert loaded.pending_merge_rel_path == Path("pending-merges.d")


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            ext_src_rel_path = "sec/external-src"
            local_src_rel_path = "sec/local-src"
            odoo_version = "18.0"
            customer_shortname = "acme"
            """
        ),
        ".proj.cfg": dedent(
            """\
            [conf]
            local_src_rel_path = cfg/local-src
            company_git_remote = acme
            """
        ),
    }
)
def test_pyproject_overrides_proj_cfg(project):
    loaded = load_config()
    assert loaded.local_src_rel_path == Path("sec/local-src")
    assert loaded.ext_src_rel_path == Path("sec/external-src")
    assert loaded.company_git_remote == "acme"
    assert loaded.odoo_src_rel_path == Path("odoo/src")


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            odoo_version = "18.0"
            company_git_remote = "sec-remote"
            """
        ),
        ".cookiecutter.context.yml": dedent(
            """\
            odoo_version: '16.0'
            customer_shortname: acme
            project_id: 42
            """
        ),
    }
)
def test_pyproject_overrides_manifest(project):
    loaded = load_config()
    assert loaded.odoo_version == "18.0"
    assert loaded.odoo_serie == 18
    assert loaded.customer_shortname == "acme"
    assert loaded.project_id == "42"
    assert loaded.company_git_remote == "sec-remote"
    assert loaded.local_src_rel_path == Path("odoo/local-src")


@pytest.mark.project_setup(
    legacy=True,
    extra_files={
        ".proj.cfg": dedent(
            """\
            [conf]
            company_git_remote = cfg-remote
            """
        ),
        ".cookiecutter.context.yml": dedent(
            """\
            odoo_version: '16.0'
            customer_shortname: acme
            """
        ),
    },
)
def test_manifest_and_proj_cfg_without_pyproject(project):
    assert not Path("pyproject.toml").exists()
    loaded = load_config()
    assert loaded.company_git_remote == "cfg-remote"
    assert loaded.odoo_version == "16.0"
    assert loaded.local_src_rel_path == Path("odoo/local-src")


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            odoo_version = "18.0"
            customer_shortname = "acme"
            """
        ),
    }
)
def test_pyproject_alone_only_needs_the_required_fields(project):
    loaded = load_config()
    assert loaded.odoo_version == "18.0"
    assert loaded.company_git_remote == "camptocamp"
    assert loaded.local_src_rel_path == Path("odoo/local-src")


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            odoo_version = "18.0"
            """
        ),
        ".proj.cfg": dedent(
            """\
            [conf]
            company_git_remote = cfg-remote
            """
        ),
    }
)
def test_required_field_missing_from_every_source(project):
    with pytest.raises(ProjectConfigException, match="customer_shortname") as exc:
        load_config()
    # The error names every source that was read
    assert ".proj.cfg" in str(exc.value)
    assert "tool.odoo-project" in str(exc.value)


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            odoo_version = "18.0"
            customer_shortname = "acme"
            """
        ),
        ".proj.cfg": dedent(
            """\
            [conf]
            company_git_remote = cfg-remote
            """
        ),
    }
)
def test_legacy_files_next_to_pyproject_still_warn(project, capsys):
    warn_deprecated_config_source.cache_clear()
    capsys.readouterr()  # drop anything emitted during setup
    load_config()
    assert "deprecated" in capsys.readouterr().err


@pytest.mark.project_setup(
    legacy=True,
    extra_files={
        ".cookiecutter.context.yml": dedent(
            """\
            odoo_version: 16.0
            customer_shortname: acme
            project_id: 1289
            """
        ),
    },
)
def test_unquoted_numbers_read_as_strings(project):
    loaded = load_config()
    assert loaded.odoo_version == "16.0"
    assert loaded.project_id == "1289"


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            odoo_version = "18.0"
            customer_shortname = "acme"
            """
        ),
    }
)
def test_require_unset_setting(project):
    with pytest.raises(ProjectConfigException, match="'project_id' is not set"):
        config.require("project_id")


@pytest.mark.project_setup(manifest=dict(project_id="4321"))
def test_require_set_setting(project):
    assert config.require("project_id") == "4321"


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project
            odoo_version = "18.0"
            """
        ),
    }
)
def test_malformed_pyproject(project):
    with pytest.raises(ProjectConfigException, match="pyproject.toml"):
        load_config()


@pytest.mark.project_setup(
    legacy=True,
    extra_files={".proj.cfg": "[conf]\nno equals sign here\n"},
)
def test_malformed_proj_cfg(project):
    with pytest.raises(ProjectConfigException, match=r"\.proj\.cfg"):
        load_config()


@pytest.mark.project_setup(
    legacy=True,
    extra_files={".cookiecutter.context.yml": "odoo_version: [16.0\n"},
)
def test_malformed_manifest(project):
    with pytest.raises(ProjectConfigException, match="cookiecutter"):
        load_config()


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            odoo_version = "18.0"
            customer_shortname = "acme"
            """
        ),
        ".cookiecutter.context.yml": "",
    }
)
def test_empty_manifest(project):
    assert load_config().odoo_version == "18.0"


@pytest.mark.project_setup(
    extra_files={
        "pyproject.toml": dedent(
            """\
            [tool.odoo-project]
            odoo_version = "18.0"
            """
        ),
        ".cookiecutter.context.yml": dedent(
            """\
            odoo_version: '16.0'
            customer_shortname: acme
            """
        ),
    }
)
def test_manifest_next_to_pyproject_is_read_silently(project, capsys):
    """The manifest belongs to the project template, which keeps it next to
    the section: it still fills the gaps, without a deprecation warning."""
    warn_deprecated_config_source.cache_clear()
    capsys.readouterr()  # drop anything emitted during setup
    loaded = load_config()
    assert loaded.customer_shortname == "acme"
    assert "deprecated" not in capsys.readouterr().err


@pytest.mark.project_setup(legacy=True)
def test_migrate_config(project):
    before = load_config()
    manifest = Path(DEPRECATED_MANIFEST_PATH).read_text()
    migration = migrate_config()
    # Only what differs from the defaults is written, the required settings
    # always are
    assert migration.added == {
        "version_file_rel_path": "odoo/VERSION",
        "marabunta_mig_file_rel_path": "odoo/migration.yml",
        "odoo_version": "14.0",
        "customer_shortname": "acme",
        "project_name": "acme_odoo",
        "project_id": "1234",
        "country": "ch",
        "odoo_main_lang": "de_DE",
        "odoo_aux_langs": "fr_CH;it_IT",
    }
    assert read_pyproject_section() == migration.added
    # A new pyproject.toml gets no empty [tool] table
    assert Path("pyproject.toml").read_text().startswith("[tool.odoo-project]\n")
    assert migration.removed_proj_cfg
    assert not Path(".proj.cfg").exists()
    # The manifest is the project template's: it is left as it was
    assert Path(DEPRECATED_MANIFEST_PATH).read_text() == manifest
    # The project reads the same configuration as before
    assert load_config() == before


@pytest.mark.project_setup(
    legacy=True,
    extra_files={
        "pyproject.toml": dedent(
            """\
            # Project tooling
            [project]
            name = "acme_odoo"

            [tool.ruff]
            line-length = 88  # keep in sync with black

            [tool.odoo-project]
            odoo_version = "18.0"  # upgraded
            """
        ),
    },
)
def test_migrate_config_keeps_pyproject_and_its_section(project):
    migration = migrate_config()
    # The section's own settings win over the legacy ones
    assert "odoo_version" not in migration.added
    assert load_config().odoo_version == "18.0"
    assert Path("pyproject.toml").read_text() == dedent(
        """\
        # Project tooling
        [project]
        name = "acme_odoo"

        [tool.ruff]
        line-length = 88  # keep in sync with black

        [tool.odoo-project]
        odoo_version = "18.0"  # upgraded
        version_file_rel_path = "odoo/VERSION"
        marabunta_mig_file_rel_path = "odoo/migration.yml"
        customer_shortname = "acme"
        project_name = "acme_odoo"
        project_id = "1234"
        country = "ch"
        odoo_main_lang = "de_DE"
        odoo_aux_langs = "fr_CH;it_IT"
        """
    )


@pytest.mark.project_setup(
    legacy=True,
    extra_files={
        ".proj.cfg": dedent(
            """\
            [conf]
            local_src_rel_path = odoo/addons
            some_old_key = foo
            """
        ),
    },
)
def test_migrate_config_reports_unknown_proj_cfg_keys(project):
    migration = migrate_config()
    assert migration.added["local_src_rel_path"] == "odoo/addons"
    assert migration.dropped == ["some_old_key"]
    assert "some_old_key" not in Path("pyproject.toml").read_text()


@pytest.mark.project_setup(
    legacy=True,
    extra_files={
        ".cookiecutter.context.yml": "odoo_version: '16.0'\n",
    },
)
def test_migrate_config_writes_nothing_when_invalid(project):
    with pytest.raises(ProjectConfigException, match="customer_shortname"):
        migrate_config()
    assert Path(".proj.cfg").exists()
    assert not Path("pyproject.toml").exists()


def test_migrate_config_nothing_to_migrate(project):
    content = Path("pyproject.toml").read_text()
    migration = migrate_config()
    assert not migration.changed
    assert Path("pyproject.toml").read_text() == content
