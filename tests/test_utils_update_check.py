# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import responses

from odoo_tools.utils import update_check


@pytest.fixture(autouse=True)
def allow_update_check(monkeypatch):
    """Re-enable the update check for this module.

    ``tests/conftest.py`` sets ``OTOOLS_SKIP_UPDATE_CHECK`` globally to
    keep the check out of every other test; unset it here so the tests
    that exercise the check itself actually run.
    """
    monkeypatch.delenv("OTOOLS_SKIP_UPDATE_CHECK", raising=False)


@pytest.fixture
def cache_dir(tmp_path):
    """Redirect the update-check cache to a temp directory."""
    with patch.object(update_check, "get_cache_path", return_value=tmp_path):
        yield tmp_path


@pytest.fixture
def mocked_releases():
    with responses.RequestsMock() as rsps:
        yield rsps


def _add_release(rsps, tag):
    rsps.add(
        responses.GET,
        update_check.RELEASES_URL,
        json={"tag_name": tag},
        status=200,
        content_type="application/json",
    )


def test_fetch_writes_cache(cache_dir, mocked_releases):
    _add_release(mocked_releases, "1.2.3")
    assert update_check.get_latest_version() == "1.2.3"
    cached = json.loads((cache_dir / update_check.CACHE_FILE_NAME).read_text())
    assert cached["latest_version"] == "1.2.3"


def test_tag_v_prefix_is_stripped(cache_dir, mocked_releases):
    _add_release(mocked_releases, "v2.0.0")
    assert update_check.get_latest_version() == "2.0.0"


def test_fresh_cache_skips_network(cache_dir):
    (cache_dir / update_check.CACHE_FILE_NAME).write_text(
        json.dumps(
            {
                "checked_at": datetime.now().isoformat(),
                "latest_version": "5.0.0",
            }
        )
    )
    # No mocked response — a real request would raise ConnectionError
    with responses.RequestsMock():
        assert update_check.get_latest_version() == "5.0.0"


def test_stale_cache_triggers_refetch(cache_dir, mocked_releases):
    stale = datetime.now() - timedelta(hours=25)
    (cache_dir / update_check.CACHE_FILE_NAME).write_text(
        json.dumps({"checked_at": stale.isoformat(), "latest_version": "0.1.0"})
    )
    _add_release(mocked_releases, "9.9.9")
    assert update_check.get_latest_version() == "9.9.9"


def test_network_error_returns_none(cache_dir, mocked_releases):
    mocked_releases.add(responses.GET, update_check.RELEASES_URL, status=500)
    assert update_check.get_latest_version() is None
    assert not (cache_dir / update_check.CACHE_FILE_NAME).exists()


def test_malformed_cache_falls_back_to_fetch(cache_dir, mocked_releases):
    (cache_dir / update_check.CACHE_FILE_NAME).write_text("not-json")
    _add_release(mocked_releases, "1.0.0")
    assert update_check.get_latest_version() == "1.0.0"


@pytest.mark.parametrize(
    "current,latest,expected",
    [
        ("0.13.0", "0.14.0", True),
        ("0.14.0", "0.13.0", False),
        ("0.14.0", "0.14.0", False),
        # Dev build of a newer series vs. older release: dev is ahead.
        ("0.14.0.dev1+gabcdef", "0.13.0", False),
        # Dev build is outdated once its base version is released.
        ("0.15.0.dev1+gabcdef", "0.15.0", True),
        # Dev build is outdated when a later release is out.
        ("0.14.0.dev1+gabcdef", "0.15.0", True),
        # Unparsable version: never warn, never crash.
        ("not-a-version", "1.0.0", False),
    ],
)
def test_compare(current, latest, expected):
    assert update_check._compare(current, latest) is expected


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("/home/user/.local/pipx/venvs/odoo-tools", "pipx upgrade odoo-tools"),
        (
            "/home/user/.local/share/uv/tools/odoo-tools",
            "uv tool upgrade odoo-tools",
        ),
        (
            "/home/user/venvs/something",
            f"pip install --upgrade git+{update_check.REPO_URL}",
        ),
    ],
)
def test_upgrade_command(prefix, expected):
    assert update_check.upgrade_command(prefix) == expected


def test_check_for_update_prints_warning(cache_dir, mocked_releases, capsys):
    _add_release(mocked_releases, "99.0.0")
    with patch.object(update_check, "__version__", "0.13.0"):
        update_check.check_for_update()
    captured = capsys.readouterr()
    assert "99.0.0" in captured.err
    assert "odoo-tools" in captured.err


def test_check_for_update_silent_when_up_to_date(cache_dir, mocked_releases, capsys):
    _add_release(mocked_releases, "0.13.0")
    with patch.object(update_check, "__version__", "0.13.0"):
        update_check.check_for_update()
    assert capsys.readouterr().err == ""


def test_skip_via_env_var(cache_dir, monkeypatch, capsys):
    monkeypatch.setenv(update_check.SKIP_ENV_VAR, "1")
    with responses.RequestsMock():  # would fail on any HTTP call
        update_check.check_for_update()
    assert capsys.readouterr().err == ""
    assert not (cache_dir / update_check.CACHE_FILE_NAME).exists()


def test_check_silent_when_fetch_fails(cache_dir, mocked_releases, capsys):
    mocked_releases.add(responses.GET, update_check.RELEASES_URL, status=500)
    update_check.check_for_update()
    assert capsys.readouterr().err == ""


def test_check_for_update_suggests_detected_install_method(
    cache_dir, mocked_releases, capsys
):
    _add_release(mocked_releases, "99.0.0")
    with (
        patch.object(update_check, "__version__", "0.13.0"),
        patch.object(
            update_check, "upgrade_command", return_value="pipx upgrade odoo-tools"
        ),
    ):
        update_check.check_for_update()
    assert "pipx upgrade odoo-tools" in capsys.readouterr().err


def test_with_update_check_decorator_invokes_check():
    calls = []

    def fake_check():
        calls.append("checked")

    @update_check.with_update_check
    def command(x, y=2):
        return x + y

    with patch.object(update_check, "check_for_update", fake_check):
        result = command(1, y=4)

    assert result == 5
    assert calls == ["checked"]
