# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path
from unittest.mock import patch

import click
import pytest

from odoo_tools.exceptions import ProjectConfigException, ProjectRootFolderNotFound
from odoo_tools.utils import minimum_version
from odoo_tools.utils.config import ProjectConfig


def _fake_config(otools_min_version: str = "") -> ProjectConfig:
    return ProjectConfig(
        company_git_remote="camptocamp",
        odoo_src_rel_path=Path("odoo/src"),
        ext_src_rel_path=Path("odoo/external-src"),
        local_src_rel_path=Path("odoo/local-src"),
        pending_merge_rel_path=Path("pending-merges.d"),
        otools_min_version=otools_min_version,
    )


def _mock_config(**attrs):
    """Patch ``config`` attribute access to return the given values.

    Anything not in ``attrs`` raises ``AttributeError`` when accessed,
    which mirrors how the real ``LazyConfig`` behaves when the loaded
    ``ProjectConfig`` lacks that field.
    """

    class _FakeConfig:
        def __getattr__(self, name):
            if name in attrs:
                return attrs[name]
            raise AttributeError(name)

    return patch.object(minimum_version, "config", _FakeConfig())


def test_no_config_is_noop():
    with patch.object(
        type(minimum_version.config),
        "__getattr__",
        side_effect=ProjectConfigException("no .proj.cfg"),
    ):
        minimum_version.check_minimum_version()


def test_outside_project_root_is_noop():
    with patch.object(
        type(minimum_version.config),
        "__getattr__",
        side_effect=ProjectRootFolderNotFound("no marker"),
    ):
        minimum_version.check_minimum_version()


def test_unset_minimum_version_is_noop():
    with _mock_config(otools_min_version=None):
        minimum_version.check_minimum_version()


def test_installed_version_meets_minimum():
    with (
        _mock_config(otools_min_version="0.10.0"),
        patch.object(minimum_version, "__version__", "0.14.0"),
    ):
        minimum_version.check_minimum_version()


def test_installed_version_equal_to_minimum_passes():
    with (
        _mock_config(otools_min_version="0.14.0"),
        patch.object(minimum_version, "__version__", "0.14.0"),
    ):
        minimum_version.check_minimum_version()


def test_installed_version_below_minimum_raises():
    with (
        _mock_config(otools_min_version="0.14.0"),
        patch.object(minimum_version, "__version__", "0.13.0"),
        patch.object(
            minimum_version,
            "upgrade_command",
            return_value="uv tool upgrade odoo-tools",
        ),
        pytest.raises(click.ClickException) as excinfo,
    ):
        minimum_version.check_minimum_version()
    message = excinfo.value.message
    assert "0.14.0" in message
    assert "0.13.0" in message
    assert "uv tool upgrade odoo-tools" in message


def test_dev_build_ahead_of_minimum_passes():
    """A dev build of a newer series is considered newer than the base."""
    with (
        _mock_config(otools_min_version="0.14.0"),
        patch.object(minimum_version, "__version__", "0.15.0.dev1+gabcdef"),
    ):
        minimum_version.check_minimum_version()


def test_decorator_invokes_check():
    calls = []

    def fake_check():
        calls.append("checked")

    @minimum_version.with_minimum_version_check
    def command(x):
        return x * 2

    with patch.object(minimum_version, "check_minimum_version", fake_check):
        result = command(3)

    assert result == 6
    assert calls == ["checked"]


def test_decorator_propagates_failure():
    def failing_check():
        raise click.ClickException("nope")

    @minimum_version.with_minimum_version_check
    def command():
        return "should not run"

    with (
        patch.object(minimum_version, "check_minimum_version", failing_check),
        pytest.raises(click.ClickException),
    ):
        command()


@pytest.mark.parametrize(
    "value",
    ["0.14.0", "1.2.3", "0.14.0.dev1"],
)
def test_config_accepts_valid_minimum_version(value):
    cfg = _fake_config(otools_min_version=value)
    assert cfg.otools_min_version == value


def test_config_rejects_malformed_minimum_version():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _fake_config(otools_min_version="not-a-version")


def test_config_empty_minimum_version_is_none():
    cfg = _fake_config(otools_min_version="")
    assert cfg.otools_min_version is None
