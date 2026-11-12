# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import subprocess
from pathlib import Path
from unittest.mock import patch

import git
import pytest

from odoo_tools.utils import gh as gh_utils

from .common import MockSubprocessRun, mock_subprocess


class TestParseGithubUrl:
    def test_full_pull_url(self):
        url = "https://github.com/OCA/edi/pull/731"
        result = gh_utils.parse_github_url(url)
        assert result == {
            "upstream": "OCA",
            "repo_name": "edi",
            "entity_type": "pull",
            "entity_id": "731",
            "is_patch": False,
        }

    def test_short_ref(self):
        result = gh_utils.parse_github_url("OCA/edi#731")
        assert result == {
            "upstream": "OCA",
            "repo_name": "edi",
            "entity_type": "pull",
            "entity_id": "731",
            "is_patch": False,
        }

    def test_commit_url(self):
        sha = "8f3a3a3bfa6c97984cad7f63e1f288841c4f7eda"
        url = f"https://github.com/OCA/edi/commit/{sha}"
        result = gh_utils.parse_github_url(url)
        assert result == {
            "upstream": "OCA",
            "repo_name": "edi",
            "entity_type": "commit",
            "entity_id": sha,
            "is_patch": False,
        }

    def test_tree_url(self):
        url = "https://github.com/OCA/edi/tree/16.0"
        result = gh_utils.parse_github_url(url)
        assert result == {
            "upstream": "OCA",
            "repo_name": "edi",
            "entity_type": "tree",
            "entity_id": "16.0",
            "is_patch": False,
        }

    def test_url_with_trailing_garbage(self):
        url = "https://github.com/OCA/edi/pull/731/files#diff-deadbeef"
        result = gh_utils.parse_github_url(url)
        assert result["upstream"] == "OCA"
        assert result["repo_name"] == "edi"
        assert result["entity_type"] == "pull"
        assert result["entity_id"] == "731"

    def test_patch_pull_url(self):
        result = gh_utils.parse_github_url("https://github.com/OCA/edi/pull/731.patch")
        assert result["entity_id"] == "731"
        assert result["is_patch"] is True

    def test_oca_lowercase_is_uppercased(self):
        result = gh_utils.parse_github_url("oca/edi#731")
        assert result["upstream"] == "OCA"

    def test_oca_mixed_case_is_uppercased(self):
        result = gh_utils.parse_github_url("Oca/edi#731")
        assert result["upstream"] == "OCA"

    def test_non_oca_upstream_preserved(self):
        result = gh_utils.parse_github_url("camptocamp/edi#731")
        assert result["upstream"] == "camptocamp"

    def test_invalid_url_raises_value_error(self):
        with pytest.raises(ValueError, match="Could not parse"):
            gh_utils.parse_github_url("not-a-url")

    def test_incomplete_url_raises_value_error(self):
        with pytest.raises(ValueError, match="Could not parse"):
            gh_utils.parse_github_url("https://github.com/OCA")


@pytest.mark.project_setup(git_init=True)
@pytest.mark.usefixtures("project")
class TestGetCurrentRebaseBranch:
    def test_returns_none_when_no_rebase(self):
        assert gh_utils.get_current_rebase_branch() is None

    def test_returns_branch_during_rebase(self):
        cwd = Path()
        repo = git.Repo(cwd)
        # Create two branches with conflicting changes to trigger a rebase conflict
        base_branch = repo.create_head("base-branch")
        base_branch.checkout()
        (cwd / "file.txt").write_text("base content\n")
        repo.index.add(["file.txt"])
        repo.index.commit("base change")

        rebase_branch = repo.create_head("rebase-branch")
        rebase_branch.checkout()
        (cwd / "file.txt").write_text("rebase content\n")
        repo.index.add(["file.txt"])
        repo.index.commit("rebase change")

        base_branch.checkout()
        (cwd / "file.txt").write_text("conflict content\n")
        repo.index.add(["file.txt"])
        repo.index.commit("conflict change")

        rebase_branch.checkout()
        # GitPython doesn't have a rebase API, so we use subprocess here
        result = subprocess.run(
            ["git", "rebase", "base-branch"],
            capture_output=True,
        )
        assert result.returncode != 0, "Expected rebase conflict"
        assert gh_utils.get_current_rebase_branch() == "rebase-branch"


@pytest.mark.project_setup(git_init=True)
@pytest.mark.usefixtures("project")
class TestGetTargetBranch:
    def test_generates_branch_name(self):
        repo = git.Repo(".")
        repo.create_head("feature-x").checkout()
        commit_sha = repo.head.commit.hexsha[:8]
        result = gh_utils.get_target_branch()
        assert result == f"merge-branch-1234-feature-x-{commit_sha}"

    def test_uses_given_target_branch(self):
        repo = git.Repo(".")
        repo.create_head("feature-x").checkout()
        result = gh_utils.get_target_branch(target_branch="custom-branch")
        assert result == "custom-branch"

    def test_asks_confirmation_on_master(self):
        with patch.object(gh_utils.ui, "ask_or_abort") as mock_ask:
            gh_utils.get_target_branch()
            mock_ask.assert_called_once()

    def test_asks_confirmation_on_version_branch(self):
        repo = git.Repo(".")
        repo.create_head("feature-x").checkout()
        with patch.object(gh_utils.ui, "ask_or_abort") as mock_ask:
            gh_utils.get_target_branch(target_branch="16.0")
            mock_ask.assert_called_once()


class TestParseRemoteUrl:
    @pytest.mark.parametrize(
        "url, expected",
        [
            ("git@github.com:OCA/edi.git", ("OCA", "edi")),
            ("git@github.com:OCA/edi", ("OCA", "edi")),
            ("https://github.com/OCA/edi.git", ("OCA", "edi")),
            ("https://github.com/OCA/edi", ("OCA", "edi")),
            ("http://github.com/OCA/edi.git", ("OCA", "edi")),
        ],
    )
    def test_valid(self, url, expected):
        assert gh_utils.parse_remote_url(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "git@gitlab.com:OCA/edi.git",
            "https://example.com/OCA/edi",
            "OCA/edi",
        ],
    )
    def test_invalid_raises(self, url):
        with pytest.raises(ValueError):
            gh_utils.parse_remote_url(url)


@pytest.mark.project_setup(git_init=True)
@pytest.mark.usefixtures("project")
class TestCheckGitDiff:
    def test_clean_repo_returns_false(self):
        assert gh_utils.check_git_diff() is False

    def test_unstaged_changes_returns_true(self):
        Path("requirements.txt").write_text("modified")
        assert gh_utils.check_git_diff() is True

    def test_staged_changes_returns_true(self):
        repo = git.Repo(".")
        Path("requirements.txt").write_text("modified")
        repo.index.add(["requirements.txt"])
        assert gh_utils.check_git_diff() is True


class TestGetToken:
    @pytest.fixture(autouse=True)
    def no_env_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def test_env_token_wins(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "env-token")
        monkeypatch.setattr(gh_utils, "_get_gh_cli_token", lambda: "cli-token")
        assert gh_utils.get_token() == "env-token"

    def test_github_token_wins_over_gh_token(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "github-token")
        monkeypatch.setenv("GH_TOKEN", "gh-token")
        assert gh_utils.get_token() == "github-token"

    def test_gh_token_wins_over_gh_cli(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "gh-token")
        monkeypatch.setattr(gh_utils, "_get_gh_cli_token", lambda: "cli-token")
        assert gh_utils.get_token() == "gh-token"

    def test_falls_back_to_gh_cli(self, monkeypatch):
        monkeypatch.setattr(gh_utils, "_get_gh_cli_token", lambda: "cli-token")
        assert gh_utils.get_token() == "cli-token"

    def test_none_when_nothing_available(self):
        assert gh_utils.get_token() is None


class TestGetGhCliToken:
    @pytest.fixture(autouse=True)
    def gh_installed(self, monkeypatch):
        monkeypatch.setattr(gh_utils, "has_exec", lambda name: name == "gh")

    def test_gh_not_installed(self, monkeypatch):
        monkeypatch.setattr(gh_utils, "has_exec", lambda name: False)
        assert gh_utils._get_gh_cli_token() is None

    @pytest.mark.parametrize(
        ("returncode", "stdout", "expected"),
        [
            (0, "gho_abc\n", "gho_abc"),
            (1, "", None),  # not logged in
        ],
    )
    def test_reads_gh_auth_token(self, returncode, stdout, expected):
        mock_fn = MockSubprocessRun(
            [
                {
                    "args": ["gh", "auth", "token", "--hostname", "github.com"],
                    "stdout": stdout,
                    "returncode": returncode,
                }
            ]
        )
        with mock_subprocess(mock_fn):
            assert gh_utils._get_gh_cli_token() == expected
        mock_fn.assert_completed_calls()
