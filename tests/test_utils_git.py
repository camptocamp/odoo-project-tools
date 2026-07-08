# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import subprocess
from pathlib import Path
from unittest import mock

import git
import pytest

from odoo_tools.exceptions import ProjectConfigException
from odoo_tools.utils import git as git_utils
from odoo_tools.utils import proj as proj_utils

from .common import MockSubprocessRun, get_fixture_path

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_autoshare_repo(repo_dir):
    """Return a mock AutoshareRepository whose repo_dir is the given path."""
    ar = mock.Mock()
    ar.repo_dir = str(repo_dir)
    return ar


# ── get_project_id (proj utils) ───────────────────────────────────────────────


@pytest.mark.project_setup(
    manifest=dict(odoo_version="18.0", project_id="1289"),
    proj_version="18.0.1.0.0",
)
def test_get_project_id_from_manifest(project):
    assert proj_utils.get_project_id() == "1289"


@pytest.mark.project_setup(
    manifest=dict(odoo_version="18.0", project_id=None),
    proj_version="18.0.1.0.0",
)
def test_get_project_id_not_set(project):
    assert proj_utils.get_project_id(raise_if_missing=False) is None
    with pytest.raises(ProjectConfigException):
        proj_utils.get_project_id()


# ── _repo_name_from_url ───────────────────────────────────────────────────────


def test_repo_name_from_url_ssh():
    assert (
        git_utils._repo_name_from_url("git@github.com:OCA/account-payment.git")
        == "account-payment"
    )


def test_repo_name_from_url_camptocamp():
    assert (
        git_utils._repo_name_from_url("git@github.com:camptocamp/storage.git")
        == "storage"
    )


def test_repo_name_from_url_trailing_slash():
    assert git_utils._repo_name_from_url("git@github.com:OCA/foo.git/") == "foo"


# ── remote_exists ────────────────────────────────────────────────────────────


def test_remote_exists_true():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(returncode=0)
        assert git_utils.remote_exists("/some/path", "OCA") is True
        mock_run.assert_called_once_with(
            ["git", "-C", "/some/path", "remote", "get-url", "OCA"],
            capture_output=True,
        )


def test_remote_exists_false():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(returncode=128)
        assert git_utils.remote_exists("/some/path", "OCA") is False


# ── ensure_remote ─────────────────────────────────────────────────────────────


def test_ensure_remote_adds_when_missing():
    with (
        mock.patch("odoo_tools.utils.git.remote_exists", return_value=False),
        mock.patch("odoo_tools.utils.git.run") as mock_run,
    ):
        result = git_utils.ensure_remote("/repo", "OCA", "git@github.com:OCA/foo.git")
        assert result is True
        mock_run.assert_called_once_with(
            [
                "git",
                "-C",
                "/repo",
                "remote",
                "add",
                "OCA",
                "git@github.com:OCA/foo.git",
            ],
            check=True,
        )


def test_ensure_remote_skips_when_present():
    with (
        mock.patch("odoo_tools.utils.git.remote_exists", return_value=True),
        mock.patch("odoo_tools.utils.git.run") as mock_run,
    ):
        result = git_utils.ensure_remote("/repo", "OCA", "git@github.com:OCA/foo.git")
        assert result is False
        mock_run.assert_not_called()


# ── get_remotes ───────────────────────────────────────────────────────────────


def test_get_remotes():
    output = (
        "OCA\tgit@github.com:OCA/edi.git (fetch)\n"
        "OCA\tgit@github.com:OCA/edi.git (push)\n"
        "camptocamp\tgit@github.com:camptocamp/edi.git (fetch)\n"
        "camptocamp\tgit@github.com:camptocamp/edi.git (push)"
    )
    with mock.patch("odoo_tools.utils.git.run", return_value=output) as mock_run:
        remotes = git_utils.get_remotes("/repo")
        mock_run.assert_called_once_with(
            ["git", "-C", "/repo", "remote", "-v"], check=True
        )
    assert remotes == {
        "OCA": "git@github.com:OCA/edi.git",
        "camptocamp": "git@github.com:camptocamp/edi.git",
    }


# ── fetch_targeted ────────────────────────────────────────────────────────────


def test_fetch_targeted_success():
    with mock.patch("odoo_tools.utils.git.run") as mock_run:
        git_utils.fetch_targeted(
            "/repo", "OCA", "+refs/heads/18.0:refs/remotes/OCA/18.0"
        )
        mock_run.assert_called_once_with(
            [
                "git",
                "-C",
                "/repo",
                "fetch",
                "OCA",
                "+refs/heads/18.0:refs/remotes/OCA/18.0",
            ],
            check=True,
        )


def test_fetch_targeted_warns_on_failure():
    with (
        mock.patch(
            "odoo_tools.utils.git.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ),
        mock.patch("odoo_tools.utils.git.ui.echo") as mock_echo,
    ):
        git_utils.fetch_targeted(
            "/repo", "OCA", "+refs/heads/18.0:refs/remotes/OCA/18.0"
        )
        assert mock_echo.called
        assert "WARNING" in mock_echo.call_args[0][0]


# ── setup_submodule_remotes ───────────────────────────────────────────────────


def test_setup_submodule_remotes_with_project_id():
    with (
        mock.patch("odoo_tools.utils.git.remote_exists", return_value=False),
        mock.patch("odoo_tools.utils.git.ensure_remote") as mock_ensure,
        mock.patch("odoo_tools.utils.git.fetch_targeted") as mock_fetch,
        mock.patch("odoo_tools.utils.git.remote_repo_exists", return_value=True),
    ):
        git_utils.setup_submodule_remotes(
            "/cache/account-payment",
            "git@github.com:camptocamp/account-payment.git",
            "18.0",
            "1289",
            "camptocamp",
        )
        assert mock_ensure.call_count == 2
        mock_ensure.assert_any_call(
            "/cache/account-payment", "OCA", "git@github.com:OCA/account-payment.git"
        )
        mock_ensure.assert_any_call(
            "/cache/account-payment",
            "camptocamp",
            "git@github.com:camptocamp/account-payment.git",
        )
        assert mock_fetch.call_count == 2
        mock_fetch.assert_any_call(
            "/cache/account-payment",
            "OCA",
            "+refs/heads/18.0:refs/remotes/OCA/18.0",
        )
        mock_fetch.assert_any_call(
            "/cache/account-payment",
            "camptocamp",
            "+refs/heads/merge-branch-1289-*:refs/remotes/camptocamp/merge-branch-1289-*",
        )


def test_setup_submodule_remotes_without_project_id():
    with (
        mock.patch("odoo_tools.utils.git.remote_exists", return_value=False),
        mock.patch("odoo_tools.utils.git.ensure_remote") as mock_ensure,
        mock.patch("odoo_tools.utils.git.fetch_targeted") as mock_fetch,
        mock.patch("odoo_tools.utils.git.remote_repo_exists", return_value=True),
    ):
        git_utils.setup_submodule_remotes(
            "/cache/account-payment",
            "git@github.com:camptocamp/account-payment.git",
            "18.0",
            None,
            "camptocamp",
        )
        # Only OCA should be set up; camptocamp fetch is skipped when project_id is None
        mock_ensure.assert_called_once_with(
            "/cache/account-payment", "OCA", "git@github.com:OCA/account-payment.git"
        )
        mock_fetch.assert_called_once_with(
            "/cache/account-payment",
            "OCA",
            "+refs/heads/18.0:refs/remotes/OCA/18.0",
        )


def test_setup_submodule_remotes_skips_missing_oca():
    """Regression test for #230.

    A non-OCA submodule (e.g. a private ``camptocamp/odoo-tools`` module) has no
    ``OCA/odoo-tools`` counterpart, so the OCA remote must not be added. The
    company remote, which does exist, is still set up.
    """

    def repo_exists(url):
        return not url.startswith("git@github.com:OCA/")

    with (
        mock.patch("odoo_tools.utils.git.remote_exists", return_value=False),
        mock.patch("odoo_tools.utils.git.ensure_remote") as mock_ensure,
        mock.patch("odoo_tools.utils.git.fetch_targeted") as mock_fetch,
        mock.patch("odoo_tools.utils.git.remote_repo_exists", side_effect=repo_exists),
    ):
        git_utils.setup_submodule_remotes(
            "/cache/odoo-tools",
            "git@github.com:camptocamp/odoo-tools.git",
            "18.0",
            "1289",
            "camptocamp",
        )
        # OCA remote must NOT be added (OCA/odoo-tools does not exist)
        mock_ensure.assert_called_once_with(
            "/cache/odoo-tools",
            "camptocamp",
            "git@github.com:camptocamp/odoo-tools.git",
        )
        mock_fetch.assert_called_once_with(
            "/cache/odoo-tools",
            "camptocamp",
            "+refs/heads/merge-branch-1289-*:refs/remotes/camptocamp/merge-branch-1289-*",
        )


def test_setup_submodule_remotes_skips_missing_company_fork():
    """A submodule without a company fork must not get a dangling company remote."""

    def repo_exists(url):
        return url.startswith("git@github.com:OCA/")

    with (
        mock.patch("odoo_tools.utils.git.remote_exists", return_value=False),
        mock.patch("odoo_tools.utils.git.ensure_remote") as mock_ensure,
        mock.patch("odoo_tools.utils.git.fetch_targeted") as mock_fetch,
        mock.patch("odoo_tools.utils.git.remote_repo_exists", side_effect=repo_exists),
    ):
        git_utils.setup_submodule_remotes(
            "/cache/account-payment",
            "git@github.com:OCA/account-payment.git",
            "18.0",
            "1289",
            "camptocamp",
        )
        # Only the OCA remote is set up; the missing company fork is skipped
        mock_ensure.assert_called_once_with(
            "/cache/account-payment", "OCA", "git@github.com:OCA/account-payment.git"
        )
        mock_fetch.assert_called_once_with(
            "/cache/account-payment",
            "OCA",
            "+refs/heads/18.0:refs/remotes/OCA/18.0",
        )


def test_setup_submodule_remotes_skips_probe_when_remote_present():
    """When the remotes are already configured locally, skip the network probe."""
    with (
        mock.patch("odoo_tools.utils.git.remote_exists", return_value=True),
        mock.patch("odoo_tools.utils.git.ensure_remote") as mock_ensure,
        mock.patch("odoo_tools.utils.git.fetch_targeted") as mock_fetch,
        mock.patch("odoo_tools.utils.git.remote_repo_exists") as mock_probe,
    ):
        git_utils.setup_submodule_remotes(
            "/cache/account-payment",
            "git@github.com:camptocamp/account-payment.git",
            "18.0",
            "1289",
            "camptocamp",
        )
        # No network probe when both remotes are already present
        mock_probe.assert_not_called()
        # Both remotes are still (idempotently) ensured and re-fetched
        assert mock_ensure.call_count == 2
        assert mock_fetch.call_count == 2


# ── remote_repo_exists ────────────────────────────────────────────────────────


def test_remote_repo_exists_true():
    git_utils.remote_repo_exists.cache_clear()
    with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0)) as mock_run:
        assert git_utils.remote_repo_exists("git@github.com:OCA/account-payment.git")
        mock_run.assert_called_once_with(
            ["git", "ls-remote", "git@github.com:OCA/account-payment.git"],
            capture_output=True,
        )


def test_remote_repo_exists_false():
    git_utils.remote_repo_exists.cache_clear()
    with mock.patch("subprocess.run", return_value=mock.Mock(returncode=128)):
        assert not git_utils.remote_repo_exists("git@github.com:OCA/odoo-tools.git")


# ── get_pinned_sha ────────────────────────────────────────────────────────────


def test_get_pinned_sha_returns_commit():
    ls_tree_output = "160000 commit abc123def456\todoo/external-src/foo"
    with mock.patch("odoo_tools.utils.git.run", return_value=ls_tree_output):
        sha = git_utils.get_pinned_sha("odoo/external-src/foo")
        assert sha == "abc123def456"


def test_get_pinned_sha_returns_none_on_empty():
    with mock.patch("odoo_tools.utils.git.run", return_value=""):
        sha = git_utils.get_pinned_sha("odoo/external-src/foo")
        assert sha is None


def test_get_pinned_sha_returns_none_on_error():
    with mock.patch(
        "odoo_tools.utils.git.run",
        side_effect=subprocess.CalledProcessError(128, "git"),
    ):
        sha = git_utils.get_pinned_sha("odoo/external-src/foo")
        assert sha is None


# ── pin_submodule_commit ──────────────────────────────────────────────────────


def test_pin_submodule_commit_when_in_store():
    with (
        mock.patch("subprocess.run") as mock_sp_run,
        mock.patch("odoo_tools.utils.git.run") as mock_run,
    ):
        mock_sp_run.return_value = mock.Mock(returncode=0)  # cat-file succeeds
        result = git_utils.pin_submodule_commit("/repo", "abc123")
        assert result is True
        mock_run.assert_called_once_with(
            ["git", "-C", "/repo", "update-ref", "refs/c2c-sync/pinned", "abc123"],
            check=True,
        )


def test_pin_submodule_commit_not_in_store():
    with (
        mock.patch("subprocess.run") as mock_sp_run,
        mock.patch("odoo_tools.utils.git.run") as mock_run,
    ):
        mock_sp_run.return_value = mock.Mock(returncode=128)  # cat-file fails
        result = git_utils.pin_submodule_commit("/repo", "abc123")
        assert result is False
        mock_run.assert_not_called()


# ── submodule_update integration ──────────────────────────────────────────────


@pytest.mark.project_setup(
    manifest=dict(odoo_version="18.0", project_id="1289"),
    proj_version="18.0.1.0.0",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_submodule_update_populates_autoshare_remotes(project, tmp_path):
    """When autoshare cache exists, setup_submodule_remotes is called on it."""
    cache_dir = tmp_path / "autoshare-cache"
    cache_dir.mkdir()
    autoshare_repo = _make_autoshare_repo(cache_dir)

    mock_fn = MockSubprocessRun(
        [
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "--reference",
                    str(cache_dir),
                    "odoo/external-src/account-closing",
                ],
            },
        ]
    )
    with (
        mock.patch("subprocess.run", mock_fn),
        mock.patch(
            "odoo_tools.utils.git.find_autoshare_repository",
            return_value=(None, autoshare_repo),
        ),
        mock.patch(
            "odoo_tools.utils.git.setup_submodule_remotes"
        ) as mock_setup_remotes,
        mock.patch("odoo_tools.utils.git.get_pinned_sha", return_value=None),
    ):
        git_utils.submodule_update("odoo/external-src/account-closing")

    # setup_submodule_remotes should have been called for the autoshare cache.
    # The base branch comes from .gitmodules — fake-gitmodules sets it to "16.0".
    mock_setup_remotes.assert_called_once_with(
        str(cache_dir),
        "git@github.com:OCA/account-closing.git",
        "16.0",
        "1289",
        "camptocamp",
    )


@pytest.mark.project_setup(
    manifest=dict(odoo_version="18.0", project_id="1289"),
    proj_version="18.0.1.0.0",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_submodule_update_pins_commit_after_clone(project, tmp_path):
    """After git submodule update, pin the recorded commit in the submodule."""
    submodule_path = Path("odoo/external-src/account-closing")
    submodule_path.mkdir(parents=True)  # simulate cloned submodule

    mock_fn = MockSubprocessRun(
        [
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "odoo/external-src/account-closing",
                ],
            },
        ]
    )
    pinned_sha = "deadbeef1234"
    with (
        mock.patch("subprocess.run", mock_fn),
        mock.patch(
            "odoo_tools.utils.git.find_autoshare_repository",
            return_value=(None, None),
        ),
        mock.patch(
            "odoo_tools.utils.git.setup_submodule_remotes"
        ) as mock_setup_remotes,
        mock.patch("odoo_tools.utils.git.get_pinned_sha", return_value=pinned_sha),
        mock.patch("odoo_tools.utils.git.pin_submodule_commit") as mock_pin,
    ):
        git_utils.submodule_update("odoo/external-src/account-closing")

    mock_setup_remotes.assert_called_once()
    mock_pin.assert_called_once()
    call_args = mock_pin.call_args[0]
    assert call_args[1] == pinned_sha


# ── get_current_branch ────────────────────────────────────────────────────────


@pytest.mark.project_setup(git_init=True)
@pytest.mark.usefixtures("project")
class TestGetCurrentBranch:
    def test_returns_branch_name(self):
        repo = git.Repo(".")
        repo.create_head("my-feature").checkout()
        assert git_utils.get_current_branch() == "my-feature"
