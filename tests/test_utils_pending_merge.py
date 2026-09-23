# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import re
import subprocess
import threading
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
from unittest import mock

import pytest
import requests
import responses
from git.config import GitConfigParser

from odoo_tools.cli import pending
from odoo_tools.exceptions import Exit, PathNotFound
from odoo_tools.utils import os_exec
from odoo_tools.utils import pending_merge as pm_utils
from odoo_tools.utils.config import config

from .common import (
    MockSubprocessRun,
    assert_no_chdir,
    mock_pending_merge_repo_paths,
    mock_subprocess,
    patch_attr,
    peak_counter,
    terminal_console,
)

Repo = pm_utils.Repo


# TODO: reuse everywhere
def compare_dict(a, b, keys=None):
    keys = keys or a.keys()
    for k in keys:
        assert a[k] == b[k], f"{k} does not match"


def test_repo_base(project):
    ext_rel_path = config.ext_src_rel_path
    pending_merge_rel_path = config.pending_merge_rel_path
    cwd = Path().resolve()
    repo = Repo("edi", path_check=False)
    expected = {
        "name": "edi",
        "company_git_remote": "camptocamp",
        "path": Path(ext_rel_path) / "edi",
        "abs_path": cwd / ext_rel_path / "edi",
        "merges_path": Path(pending_merge_rel_path) / "edi.yml",
        "abs_merges_path": cwd / pending_merge_rel_path / "edi.yml",
    }
    for k, v in expected.items():
        assert getattr(repo, k) == v, f"{k} does not match"


def test_repo_check_path(project):
    name = "edi"
    with pytest.raises(PathNotFound, match="GIT CONFIG*"):
        Repo(name)
    # Add fake git root
    mock_pending_merge_repo_paths(name, pending=False)
    with pytest.raises(PathNotFound, match="MERGES PATH*"):
        Repo(name)
    mock_pending_merge_repo_paths(name)
    assert Repo(name)


def test_repositories_from_pending_folder(project):
    names = sorted(["edi", "wms", "web-api"])
    for name in names:
        mock_pending_merge_repo_paths(name)
    repos = Repo.repositories_from_pending_folder()
    assert sorted([x.name for x in repos]) == names


def test_has_pending_merges(project):
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name)
    assert repo.has_pending_merges()


def test_merges_config(project):
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name)
    config = repo.merges_config()
    assert config["remotes"] == {
        "OCA": "git@github.com:OCA/edi.git",
        "camptocamp": "git@github.com:camptocamp/edi.git",
    }


@pytest.mark.usefixtures("all_template_versions")
@pytest.mark.project_setup(manifest=dict(odoo_version="16.0"))
def test_generate_pending_merges_file_template():
    name = "edi"
    mock_pending_merge_repo_paths(name, pending=False)
    repo = Repo(name, path_check=False)
    assert not repo.has_pending_merges()
    repo.generate_pending_merges_file_template("OCA")
    assert repo.has_pending_merges()
    expected = {
        "remotes": {
            "camptocamp": "git@github.com:camptocamp/edi.git",
            "OCA": "git@github.com:OCA/edi.git",
        },
        "target": "camptocamp merge-branch-1234-master",
        "merges": ["OCA 16.0"],
    }
    compare_dict(repo.merges_config(), expected)


@pytest.mark.usefixtures("all_template_versions")
@pytest.mark.project_setup(manifest=dict(odoo_version="16.0"))
def test_add_pending_pr_from_scratch():
    repo_name = "edi-framework"
    mock_pending_merge_repo_paths(repo_name, pending=False)
    repo = Repo(repo_name, path_check=False)
    # Setup .gitmodules pointing to the upstream (OCA)
    with Path(".gitmodules").open("w") as f:
        f.write(
            f'[submodule "{repo.path}"]\n'
            f"\tpath = {repo.path}\n"
            f"\turl = git@github.com:OCA/{repo_name}.git\n"
            f"\tbranch = 16.0\n"
        )
    repo.generate_pending_merges_file_template("OCA")
    repo.add_pending_pull_request("OCA", 778)
    expected = {
        "merges": ["OCA 16.0", "OCA refs/pull/778/head"],
        "remotes": {
            "OCA": f"git@github.com:OCA/{repo_name}.git",
            "camptocamp": f"git@github.com:camptocamp/{repo_name}.git",
        },
        "target": "camptocamp merge-branch-1234-master",
    }
    compare_dict(repo.merges_config(), expected)
    # .gitmodules should now point to the company fork
    config = GitConfigParser(".gitmodules", read_only=True)
    url = config.get(f'submodule "{repo.path}"', "url")
    assert url == f"git@github.com:camptocamp/{repo_name}.git"


@pytest.mark.usefixtures("all_template_versions")
@pytest.mark.project_setup(manifest=dict(odoo_version="16.0"))
def test_add_pending_pr_from_scratch_duplicate():
    """Adding the same PR twice should not duplicate it."""
    repo_name = "edi-framework"
    mock_pending_merge_repo_paths(repo_name, pending=False)
    repo = Repo(repo_name, path_check=False)
    with Path(".gitmodules").open("w") as f:
        f.write(
            f'[submodule "{repo.path}"]\n'
            f"\tpath = {repo.path}\n"
            f"\turl = git@github.com:OCA/{repo_name}.git\n"
            f"\tbranch = 16.0\n"
        )
    repo.generate_pending_merges_file_template("OCA")
    repo.add_pending_pull_request("OCA", 778)
    # Adding the same PR again should be a no-op
    result = repo.add_pending_pull_request("OCA", 778)
    assert result is True
    merges = repo.merges_config()["merges"]
    # PR should appear only once
    assert merges.count("OCA refs/pull/778/head") == 1


@pytest.mark.usefixtures("all_template_versions")
def test_add_pending_pr():
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    repo.add_pending_pull_request("OCA", 778)
    expected = {
        "merges": [
            "OCA 14.0",
            "OCA refs/pull/774/head",
            "OCA refs/pull/773/head",
            "OCA refs/pull/663/head",
            "OCA refs/pull/759/head",
            "OCA refs/pull/778/head",
        ],
        "remotes": {
            "OCA": "git@github.com:OCA/edi.git",
            "camptocamp": "git@github.com:camptocamp/edi.git",
        },
        "target": "camptocamp merge-branch-1234-master",
    }
    compare_dict(repo.merges_config(), expected)


@pytest.mark.usefixtures("all_template_versions")
def test_add_pending_pr_duplicate():
    """Adding a PR that already exists should be a no-op."""
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    # PR 774 already exists in the fixture
    result = repo.add_pending_pull_request("OCA", 774)
    assert result is True
    merges = repo.merges_config()["merges"]
    assert merges.count("OCA refs/pull/774/head") == 1


@pytest.mark.usefixtures("all_template_versions")
def test_add_pending_pr_multiple():
    """Adding multiple different PRs should work."""
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    repo.add_pending_pull_request("OCA", 778)
    repo.add_pending_pull_request("OCA", 779)
    merges = repo.merges_config()["merges"]
    assert "OCA refs/pull/778/head" in merges
    assert "OCA refs/pull/779/head" in merges


def test_add_pending_pr_with_comments(project):
    """A new pending merge is appended at the end of the list with its PR title
    and URL on the two comment lines above it, aligned with the merge items, and
    after the comment block of the previous entry (not in between)."""
    name = "edi"
    tmpl = """
../{ext_src_rel_path}/{repo_name}:
  remotes:
    camptocamp: git@github.com:camptocamp/{repo_name}.git
    {org_name}: git@github.com:{org_name}/{repo_name}.git
  target: camptocamp merge-branch-{pid}-master
  merges:
  - {org_name} 19.0
  # [19.0] [ADD] sale_stock_picking_backorder_policy
  # https://github.com/OCA/{repo_name}/pull/2372
  - {org_name} refs/pull/2372/head
"""
    mock_pending_merge_repo_paths(name, tmpl=tmpl)
    repo = Repo(name, path_check=False)
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/edi/pulls/2373",
            json={
                "title": "[19.0] [ADD] sale_stock_picking_backorder_split_policy",
                "html_url": "https://github.com/OCA/edi/pull/2373",
                # match the project's odoo_version so no divergent-branch prompt
                "base": {"ref": "14.0"},
            },
            status=200,
        )
        repo.add_pending_pull_request("OCA", 2373)
    expected = dedent(
        """\
        ../odoo/external-src/edi:
          remotes:
            camptocamp: git@github.com:camptocamp/edi.git
            OCA: git@github.com:OCA/edi.git
          target: camptocamp merge-branch-1234-master
          merges:
          - OCA 19.0
          # [19.0] [ADD] sale_stock_picking_backorder_policy
          # https://github.com/OCA/edi/pull/2372
          - OCA refs/pull/2372/head
          # [19.0] [ADD] sale_stock_picking_backorder_split_policy
          # https://github.com/OCA/edi/pull/2373
          - OCA refs/pull/2373/head
        """
    )
    assert repo.abs_merges_path.read_text() == expected


def test_add_pending_pr_without_title_no_comment(project):
    """When the GitHub call fails, the merge is still appended at the end but
    with no comment block (graceful degradation)."""
    name = "edi"
    tmpl = """
../{ext_src_rel_path}/{repo_name}:
  remotes:
    camptocamp: git@github.com:camptocamp/{repo_name}.git
    {org_name}: git@github.com:{org_name}/{repo_name}.git
  target: camptocamp merge-branch-{pid}-master
  merges:
  - {org_name} 19.0
  - {org_name} refs/pull/2372/head
"""
    mock_pending_merge_repo_paths(name, tmpl=tmpl)
    repo = Repo(name, path_check=False)
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/edi/pulls/2373",
            json={"message": "Not Found"},
            status=404,
        )
        repo.add_pending_pull_request("OCA", 2373)
    expected = dedent(
        """\
        ../odoo/external-src/edi:
          remotes:
            camptocamp: git@github.com:camptocamp/edi.git
            OCA: git@github.com:OCA/edi.git
          target: camptocamp merge-branch-1234-master
          merges:
          - OCA 19.0
          - OCA refs/pull/2372/head
          - OCA refs/pull/2373/head
        """
    )
    assert repo.abs_merges_path.read_text() == expected


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_add_pending_odoo_pr_v1():
    repo = Repo("odoo", path_check=False)
    # Setup .gitmodules pointing to the upstream (odoo)
    with Path(".gitmodules").open("w") as f:
        f.write(
            f'[submodule "{repo.path}"]\n'
            f"\tpath = {repo.path}\n"
            f"\turl = git@github.com:odoo/odoo.git\n"
            f"\tbranch = 14.0\n"
        )
    # 1: start with no pending merges, generate the pending merges file
    assert not repo.has_pending_merges()
    with mock.patch("odoo_tools.utils.ui.ask_confirmation", return_value=True):
        repo.generate_pending_merges_file_template("odoo")
    assert repo.has_pending_merges()
    compare_dict(
        repo.merges_config(),
        {
            "merges": [
                "odoo 14.0",
            ],
            "remotes": {
                "camptocamp": "git@github.com:camptocamp/odoo.git",
                "odoo": "git@github.com:odoo/odoo.git",
            },
            "target": "camptocamp merge-branch-1234-master",
        },
    )
    # .gitmodules should now point to the company fork
    config = GitConfigParser(".gitmodules", read_only=True)
    url = config.get(f'submodule "{repo.path}"', "url")
    assert url == "git@github.com:camptocamp/odoo.git"
    # 2: add a pending merge
    with mock.patch("odoo_tools.utils.ui.ask_confirmation", return_value=True):
        repo.add_pending_pull_request("odoo", 778)
    compare_dict(
        repo.merges_config(),
        {
            "merges": [
                "odoo 14.0",
                "odoo refs/pull/778/head",
            ],
            "remotes": {
                "camptocamp": "git@github.com:camptocamp/odoo.git",
                "odoo": "git@github.com:odoo/odoo.git",
            },
            "target": "camptocamp merge-branch-1234-master",
        },
    )


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=2)
def test_add_pending_odoo_pr_v2():
    repo = Repo("odoo", path_check=False)
    # 1: start with no pending merges, generate the pending merges file
    assert not repo.has_pending_merges()
    with mock.patch(
        "odoo_tools.utils.pending_merge.get_docker_image_commit_hashes",
        return_value=("sha-odoo", "sha-enterprise"),
    ):
        repo.generate_pending_merges_file_template("odoo")
    assert repo.has_pending_merges()
    compare_dict(
        repo.merges_config(),
        {
            "merges": [
                "odoo sha-odoo",
            ],
            "remotes": {
                "camptocamp": "git@github.com:camptocamp/odoo.git",
                "odoo": "git@github.com:odoo/odoo.git",
            },
            "target": "camptocamp merge-branch-1234-master",
        },
    )
    # attempt to add a pending pr
    with pytest.raises(Exit) as e:
        repo.add_pending_pull_request("odoo", 778)
        assert "Pull Request to Odoo repositories is not supported" in str(e)
    # it shouldn't have changed the config
    compare_dict(
        repo.merges_config(),
        {
            "merges": [
                "odoo sha-odoo",
            ],
            "remotes": {
                "camptocamp": "git@github.com:camptocamp/odoo.git",
                "odoo": "git@github.com:odoo/odoo.git",
            },
            "target": "camptocamp merge-branch-1234-master",
        },
    )


@pytest.mark.usefixtures("all_template_versions")
def test_remove_pending_pr():
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    merges = repo.merges_config().get("merges", [])
    original = [
        "OCA 14.0",
        "OCA refs/pull/774/head",
        "OCA refs/pull/773/head",
        "OCA refs/pull/663/head",
        "OCA refs/pull/759/head",
    ]
    assert merges == original
    repo.remove_pending_pull("OCA", 663)
    merges = repo.merges_config().get("merges", [])
    expected = [
        "OCA 14.0",
        "OCA refs/pull/774/head",
        "OCA refs/pull/773/head",
        "OCA refs/pull/759/head",
    ]
    assert merges == expected


@pytest.mark.usefixtures("all_template_versions")
def test_remove_pending_pr_not_found():
    """Removing a PR that doesn't exist should raise Exit."""
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    with pytest.raises(Exit):
        repo.remove_pending_pull("OCA", 999)


@pytest.mark.usefixtures("all_template_versions")
@pytest.mark.project_setup(
    manifest=dict(odoo_version="14.0"), proj_version="14.0.0.1.0"
)
def test_remove_pending_last_pr():
    """Test removing the last pending PR deletes the merges file."""
    name = "edi"
    # Template with only one pending PR (besides the base branch)
    tmpl = """
../{ext_src_rel_path}/{repo_name}:
    remotes:
        camptocamp: git@github.com:camptocamp/{repo_name}.git
        {org_name}: git@github.com:{org_name}/{repo_name}.git
    target: camptocamp merge-branch-{pid}-master
    merges:
    - {org_name} 14.0
    - {org_name} refs/pull/774/head
"""
    mock_pending_merge_repo_paths(name, tmpl=tmpl)
    repo = Repo(name, path_check=False)
    merges = repo.merges_config().get("merges", [])
    assert merges == ["OCA 14.0", "OCA refs/pull/774/head"]
    # Remove the only pending PR via the top-level function
    with mock.patch.object(Repo, "_handle_empty_merges_file") as mock_handle:
        pm_utils.remove_pending("https://github.com/OCA/edi/pull/774")
    mock_handle.assert_called_once()


@pytest.mark.project_setup(manifest=dict(odoo_version="16.0"))
def test_handle_empty_merges_file_unlink_is_idempotent(project):
    """Deleting the merges file stays safe if it is already gone (#252)."""
    name = "edi"
    mock_pending_merge_repo_paths(name, pending=False)  # no merges file on disk
    repo = Repo(name, path_check=False)
    assert not repo.abs_merges_path.exists()
    with (
        mock.patch.object(
            Repo, "merges_config", return_value={"remotes": {"OCA": "url"}}
        ),
        mock.patch.object(pm_utils, "get_new_remote_url", return_value="url"),
        mock.patch.object(pm_utils.git, "get_remotes", return_value=["OCA"]),
        mock.patch.object(pm_utils.git, "submodule_set_url"),
        mock.patch.object(pm_utils.git, "checkout"),
    ):
        # The unlink must not raise FileNotFoundError for the missing file.
        repo._handle_empty_merges_file()


@pytest.mark.project_setup(manifest=dict(odoo_version="16.0"))
def __test_add_pending_commit_from_scratch(project):
    name = "edi"
    mock_pending_merge_repo_paths(name, pending=False)
    repo = Repo(name, path_check=False)
    repo.generate_pending_merges_file_template("OCA")
    sha = "6d35e8d16afaec2f9bf8996defaf0086cd704481"
    repo.add_pending_commit("OCA", sha)
    expected = {
        "merges": ["OCA 16.0"],
        "remotes": {
            "OCA": "git@github.com:OCA/edi.git",
            "camptocamp": "git@github.com:camptocamp/edi.git",
        },
        "shell_command_after": [
            "git fetch OCA 6d35e8d16afaec2f9bf8996defaf0086cd704481",
            'git am "$(git format-patch -1 6d35e8d16afaec2f9bf8996defaf0086cd704481 -o ../patches)"',
        ],
        "target": "camptocamp merge-branch-1234-master",
    }
    compare_dict(repo.merges_config(), expected)


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_add_pending_commit_v1():
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    sha = "a86f5fe73e1f34f29cb2ad0dca253e47ce625406"
    repo.add_pending_commit("OCA", sha)
    expected = {
        "remotes": {
            "camptocamp": "git@github.com:camptocamp/edi.git",
            "OCA": "git@github.com:OCA/edi.git",
        },
        "target": "camptocamp merge-branch-1234-master",
        "merges": [
            "OCA 14.0",
            "OCA refs/pull/774/head",
            "OCA refs/pull/773/head",
            "OCA refs/pull/663/head",
            "OCA refs/pull/759/head",
        ],
        "shell_command_after": [
            "git fetch OCA a86f5fe73e1f34f29cb2ad0dca253e47ce625406",
            'git am "$(git format-patch -1 a86f5fe73e1f34f29cb2ad0dca253e47ce625406 -o ../patches)"',
        ],
    }
    compare_dict(repo.merges_config(), expected)


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_add_pending_commit_duplicate():
    """Adding a commit that already exists should be a no-op."""
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    sha = "a86f5fe73e1f34f29cb2ad0dca253e47ce625406"
    repo.add_pending_commit("OCA", sha)
    # Adding the same commit again should be a no-op
    result = repo.add_pending_commit("OCA", sha)
    assert result is True
    shell_commands = repo.merges_config().get("shell_command_after", [])
    am_line = f'git am "$(git format-patch -1 {sha} -o ../patches)"'
    assert shell_commands.count(am_line) == 1


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=2)
def test_add_pending_commit_v2():
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    sha = "a86f5fe73e1f34f29cb2ad0dca253e47ce625406"
    repo.add_pending_commit("OCA", sha)
    expected = {
        "remotes": {
            "camptocamp": "git@github.com:camptocamp/edi.git",
            "OCA": "git@github.com:OCA/edi.git",
        },
        "target": "camptocamp merge-branch-1234-master",
        "merges": [
            "OCA 14.0",
            "OCA refs/pull/774/head",
            "OCA refs/pull/773/head",
            "OCA refs/pull/663/head",
            "OCA refs/pull/759/head",
        ],
        "shell_command_after": [
            "git fetch OCA a86f5fe73e1f34f29cb2ad0dca253e47ce625406",
            "git cherry-pick a86f5fe73e1f34f29cb2ad0dca253e47ce625406",
        ],
    }
    compare_dict(repo.merges_config(), expected)


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_add_pending_odoo_commit_v1():
    repo = Repo("odoo", path_check=False)
    with mock.patch("odoo_tools.utils.ui.ask_confirmation", return_value=True):
        repo.generate_pending_merges_file_template("odoo")
    commit_sha = "abcdefg123456789abcdefg123456789abcdefg1"
    repo.add_pending_commit("odoo", commit_sha)
    compare_dict(
        repo.merges_config(),
        {
            "merges": [
                "odoo 14.0",
            ],
            "remotes": {
                "camptocamp": "git@github.com:camptocamp/odoo.git",
                "odoo": "git@github.com:odoo/odoo.git",
            },
            "target": "camptocamp merge-branch-1234-master",
            "shell_command_after": [
                f"git fetch odoo {commit_sha}",
                f'git am "$(git format-patch -1 {commit_sha} -o ../patches)"',
            ],
        },
    )


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=2)
def test_add_pending_odoo_commit_v2():
    repo = Repo("odoo", path_check=False)
    with mock.patch(
        "odoo_tools.utils.pending_merge.get_docker_image_commit_hashes",
        return_value=("sha-odoo", "sha-enterprise"),
    ):
        repo.generate_pending_merges_file_template("odoo")
    commit_sha = "abcdefg123456789abcdefg123456789abcdefg1"
    repo.add_pending_commit("odoo", commit_sha)
    compare_dict(
        repo.merges_config(),
        {
            "merges": [
                "odoo sha-odoo",
            ],
            "remotes": {
                "camptocamp": "git@github.com:camptocamp/odoo.git",
                "odoo": "git@github.com:odoo/odoo.git",
            },
            "target": "camptocamp merge-branch-1234-master",
            "shell_command_after": [
                f"git fetch odoo {commit_sha}",
                f'git am "$(git format-patch -1 {commit_sha} -o ../../patches/odoo)"',
            ],
        },
    )


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_remove_pending_commit_v1():
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    sha = "a86f5fe73e1f34f29cb2ad0dca253e47ce625406"
    repo.add_pending_commit("OCA", sha)
    shell_command_after = repo.merges_config().get("shell_command_after", [])
    assert shell_command_after == [
        "git fetch OCA a86f5fe73e1f34f29cb2ad0dca253e47ce625406",
        'git am "$(git format-patch -1 a86f5fe73e1f34f29cb2ad0dca253e47ce625406 -o ../patches)"',
    ]
    repo.remove_pending_commit("OCA", sha)
    shell_command_after = repo.merges_config().get("shell_command_after", [])
    expected = []
    assert shell_command_after == expected


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_remove_pending_commit_not_found():
    """Removing a commit that doesn't exist should raise Exit."""
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    with pytest.raises(Exit):
        repo.remove_pending_commit("OCA", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=2)
def test_remove_pending_commit_v2():
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    sha = "a86f5fe73e1f34f29cb2ad0dca253e47ce625406"
    repo.add_pending_commit("OCA", sha)
    shell_command_after = repo.merges_config().get("shell_command_after", [])
    assert shell_command_after == [
        "git fetch OCA a86f5fe73e1f34f29cb2ad0dca253e47ce625406",
        "git cherry-pick a86f5fe73e1f34f29cb2ad0dca253e47ce625406",
    ]
    repo.remove_pending_commit("OCA", sha)
    shell_command_after = repo.merges_config().get("shell_command_after", [])
    expected = []
    assert shell_command_after == expected


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_remove_pending_patch_v1():
    name = "edi"
    tmpl = """
    ../{ext_src_rel_path}/{repo_name}:
        remotes:
            camptocamp: git@github.com:camptocamp/{repo_name}.git
            {org_name}: git@github.com:{org_name}/{repo_name}.git
        target: camptocamp merge-branch-{pid}-master
        merges:
        - {org_name} 14.0
        shell_command_after:
        - curl -sSL https://github.com/OCA/edi/pull/1469.patch | git am -3 --keep-non-patch --exclude '*requirements.txt'"
    """
    mock_pending_merge_repo_paths(name, tmpl=tmpl)
    repo = Repo(name, path_check=False)
    repo.remove_pending_pull_from_patches("OCA", "1469")
    shell_command_after = repo.merges_config().get("shell_command_after", [])
    assert not shell_command_after


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_add_pending_pull_request_patch():
    """A patch is appended at the end of `shell_command_after`, either from a
    `.patch` URL or with `patch=True`, with its PR title and URL on the comment
    lines above it, just like a regular pending merge."""
    name = "edi"
    tmpl = """\
../{ext_src_rel_path}/{repo_name}:
  remotes:
    camptocamp: git@github.com:camptocamp/{repo_name}.git
    {org_name}: git@github.com:{org_name}/{repo_name}.git
  target: camptocamp merge-branch-{pid}-master
  merges:
  - {org_name} 14.0
  shell_command_after:
  # [14.0] [FIX] edi: fix 1469
  # https://github.com/OCA/edi/pull/1469
  - curl -sSL https://github.com/OCA/edi/pull/1469.patch | git am -3 --keep-non-patch --exclude '*requirements.txt'
"""
    mock_pending_merge_repo_paths(name, tmpl=tmpl)
    repo = Repo(name, path_check=False)
    with responses.RequestsMock() as rsps:
        for pid in (1470, 1471):
            rsps.add(
                responses.GET,
                f"https://api.github.com/repos/OCA/edi/pulls/{pid}",
                json={
                    "title": f"[14.0] [FIX] edi: fix {pid}",
                    "html_url": f"https://github.com/OCA/edi/pull/{pid}",
                    # match the project's odoo_version so no divergent-branch prompt
                    "base": {"ref": "14.0"},
                },
                status=200,
            )
        pm_utils.add_pending(
            "https://github.com/OCA/edi/pull/1470.patch",
            aggregate=False,
        )
        pm_utils.add_pending(
            "https://github.com/OCA/edi/pull/1471",
            patch=True,
            aggregate=False,
        )
    expected = dedent(
        """\
        ../odoo/external-src/edi:
          remotes:
            camptocamp: git@github.com:camptocamp/edi.git
            OCA: git@github.com:OCA/edi.git
          target: camptocamp merge-branch-1234-master
          merges:
          - OCA 14.0
          shell_command_after:
          # [14.0] [FIX] edi: fix 1469
          # https://github.com/OCA/edi/pull/1469
          - curl -sSL https://github.com/OCA/edi/pull/1469.patch | git am -3 --keep-non-patch --exclude '*requirements.txt'
          # [14.0] [FIX] edi: fix 1470
          # https://github.com/OCA/edi/pull/1470
          - curl -sSL https://github.com/OCA/edi/pull/1470.patch | git am -3 --keep-non-patch --exclude '*requirements.txt'
          # [14.0] [FIX] edi: fix 1471
          # https://github.com/OCA/edi/pull/1471
          - curl -sSL https://github.com/OCA/edi/pull/1471.patch | git am -3 --keep-non-patch --exclude '*requirements.txt'
        """
    )
    assert repo.abs_merges_path.read_text() == expected


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_add_pending_pull_request_patch_without_title_no_comment():
    """When the GitHub call fails, the patch is still appended at the end but
    with no comment block (graceful degradation)."""
    name = "edi"
    tmpl = """\
../{ext_src_rel_path}/{repo_name}:
  remotes:
    camptocamp: git@github.com:camptocamp/{repo_name}.git
    {org_name}: git@github.com:{org_name}/{repo_name}.git
  target: camptocamp merge-branch-{pid}-master
  merges:
  - {org_name} 14.0
"""
    mock_pending_merge_repo_paths(name, tmpl=tmpl)
    repo = Repo(name, path_check=False)
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/edi/pulls/1470",
            json={"message": "Not Found"},
            status=404,
        )
        repo.add_pending_pull_request("OCA", "1470", patch=True)
    expected = dedent(
        """\
        ../odoo/external-src/edi:
          remotes:
            camptocamp: git@github.com:camptocamp/edi.git
            OCA: git@github.com:OCA/edi.git
          target: camptocamp merge-branch-1234-master
          merges:
          - OCA 14.0
          shell_command_after:
          - curl -sSL https://github.com/OCA/edi/pull/1470.patch | git am -3 --keep-non-patch --exclude '*requirements.txt'
        """
    )
    assert repo.abs_merges_path.read_text() == expected


def test_cli_add_multiple_urls(project):
    """`otools-pending add` accepts several URLs at once, writing every entry to
    its merges file. URLs for the same submodule land in the same file."""
    mock_pending_merge_repo_paths("edi")
    mock_pending_merge_repo_paths("web")
    edi = Repo("edi", path_check=False)
    web = Repo("web", path_check=False)
    with responses.RequestsMock() as rsps:
        # match the project's odoo_version so no divergent-branch prompt
        for pull_id in (1470, 1471):
            rsps.add(
                responses.GET,
                f"https://api.github.com/repos/OCA/edi/pulls/{pull_id}",
                json={"base": {"ref": "14.0"}},
                status=200,
            )
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/web/pulls/2000",
            json={"base": {"ref": "14.0"}},
            status=200,
        )
        result = project.invoke(
            pending.add_pending,
            [
                "https://github.com/OCA/edi/pull/1470",
                "https://github.com/OCA/edi/pull/1471",
                "https://github.com/OCA/web/pull/2000",
                "--no-aggregate",
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    edi_merges = edi.merges_config()["merges"]
    assert "OCA refs/pull/1470/head" in edi_merges
    assert "OCA refs/pull/1471/head" in edi_merges
    web_merges = web.merges_config()["merges"]
    assert "OCA refs/pull/2000/head" in web_merges


def test_cli_add_multiple_urls_aggregates_once_per_submodule(project):
    """Submodules are aggregated once each, after all entries are written, even
    when several URLs target the same submodule (no intermediate aggregation)."""
    mock_pending_merge_repo_paths("edi")
    mock_pending_merge_repo_paths("web")
    with responses.RequestsMock() as rsps:
        # match the project's odoo_version so no divergent-branch prompt
        for pull_id in (1470, 1471):
            rsps.add(
                responses.GET,
                f"https://api.github.com/repos/OCA/edi/pulls/{pull_id}",
                json={"base": {"ref": "14.0"}},
                status=200,
            )
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/web/pulls/2000",
            json={"base": {"ref": "14.0"}},
            status=200,
        )
        with (
            mock.patch.object(pm_utils.Repo, "run_aggregate") as run_aggregate,
            mock.patch.object(pm_utils.Repo, "push_to_remote") as push_to_remote,
        ):
            result = project.invoke(
                pending.add_pending,
                [
                    "https://github.com/OCA/edi/pull/1470",
                    "https://github.com/OCA/edi/pull/1471",
                    "https://github.com/OCA/web/pull/2000",
                ],
                catch_exceptions=False,
            )
    assert result.exit_code == 0
    # edi is referenced twice but aggregated once: 2 unique submodules total.
    assert run_aggregate.call_count == 2
    assert push_to_remote.call_count == 2


def test_repo_run_aggregate_runs_gitaggregate_cli(project):
    mock_pending_merge_repo_paths("edi")
    repo = Repo("edi", path_check=False)
    with mock.patch.object(pm_utils, "run") as run:
        repo.run_aggregate()
    run.assert_called_once_with(
        ["gitaggregate", "--config", str(repo.abs_merges_path), "aggregate"],
        cwd=repo.pending_merge_abs_path,
        check=True,
        verbose=True,
    )


def test_cli_aggregate(project):
    mock_pending_merge_repo_paths("edi")
    with (
        mock.patch.object(pm_utils.Repo, "run_aggregate") as run_aggregate,
        mock.patch.object(pm_utils.Repo, "push_to_remote") as push_to_remote,
    ):
        result = project.invoke(pending.aggregate, ["edi"], catch_exceptions=False)
    assert result.exit_code == 0
    assert run_aggregate.called
    assert push_to_remote.called


def test_cli_aggregate_multiple_repos(project):
    """`otools-pending aggregate` accepts several repos at once, aggregating
    each of them once, and skips the ones without pending merges."""
    mock_pending_merge_repo_paths("edi")
    mock_pending_merge_repo_paths("web")
    mock_pending_merge_repo_paths("stock", pending=False)
    with (
        mock.patch.object(pm_utils.Repo, "run_aggregate") as run_aggregate,
        mock.patch.object(pm_utils.Repo, "push_to_remote") as push_to_remote,
    ):
        result = project.invoke(
            pending.aggregate,
            ["edi", "odoo/external-src/web", "stock", "edi"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    assert "Warning: stock has no pending merges, skipping." in result.output
    # edi is given twice but aggregated once, stock is left out
    assert run_aggregate.call_count == 2
    assert push_to_remote.call_count == 2


@pytest.mark.parametrize("repo_path", ["edi", "odoo/external-src/edi"])
def test_cli_aggregate_repo_without_pending_merges(project, repo_path):
    """A repo without a pending-merges file has nothing to aggregate: it is
    reported and skipped instead of blowing up."""
    mock_pending_merge_repo_paths("edi", pending=False)
    with (
        mock.patch.object(pm_utils.Repo, "run_aggregate") as run_aggregate,
        mock.patch.object(pm_utils.Repo, "push_to_remote") as push_to_remote,
    ):
        result = project.invoke(pending.aggregate, [repo_path], catch_exceptions=False)
    assert result.exit_code == 0
    assert f"Warning: {repo_path} has no pending merges, skipping." in result.output
    assert not run_aggregate.called
    assert not push_to_remote.called


def test_repo_push_to_remote(project):
    mock_pending_merge_repo_paths("edi")
    repo = Repo("edi", path_check=False)
    with (
        mock.patch.object(pm_utils, "run") as run,
        mock.patch.object(pm_utils.git, "ensure_remote") as ensure_remote,
    ):
        repo.push_to_remote(target_branch="merge-branch-1234-master-abc12345")
    ensure_remote.assert_called_once_with(
        repo.abs_path, "camptocamp", "git@github.com:camptocamp/edi.git"
    )
    run.assert_called_once_with(
        "git push -f camptocamp HEAD:refs/heads/merge-branch-1234-master-abc12345",
        cwd=repo.abs_path,
        check=True,
        verbose=True,
    )


def test_repo_run_aggregate_prints_nothing_when_captured(project, capfd):
    """Under capture_output, not a single byte may reach the terminal, even
    when the aggregation fails: it would corrupt the live progress display.

    Runs the real gitaggregate, which fails on this fake submodule -- exactly
    the case where output would otherwise be dumped on the terminal. Note that
    run_aggregate is not told about any of this.
    """
    mock_pending_merge_repo_paths("edi")
    repo = Repo("edi", path_check=False)
    lines = []
    with (
        os_exec.capture_output(lines.append),
        pytest.raises(subprocess.CalledProcessError),
    ):
        repo.run_aggregate()
    # gitaggregate did report the failure, to the sink and nowhere else
    assert any("error" in line.lower() for line in lines), lines
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_repo_push_to_remote_captures_the_remote_setup_too(project, capfd):
    """Everything the push does is captured, down to the remote bookkeeping.

    `git remote add` reports its failures through run() too, and it would
    print them behind the live display if the capture didn't reach it.
    """
    mock_pending_merge_repo_paths("edi")
    repo = Repo("edi", path_check=False)
    lines = []
    # `edi/.git` is a bare directory here, so the `git remote add` that
    # ensure_remote runs fails and complains -- on the sink, we hope.
    with os_exec.capture_output(lines.append):
        with pytest.raises(subprocess.CalledProcessError):
            repo.push_to_remote(target_branch="merge-branch-1234")
    assert any("fatal" in line.lower() for line in lines), lines
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_repo_aggregate_and_push_do_not_chdir(project):
    """Aggregating and pushing must not change the process working directory:
    they run concurrently, and chdir would corrupt the other threads' paths."""
    mock_pending_merge_repo_paths("edi")
    repo = Repo("edi", path_check=False)
    subprocess_run = MockSubprocessRun(
        [
            {"args": None},  # gitaggregate
            {"args": None},  # git remote get-url (remote_exists)
            {"args": None},  # git push
        ]
    )
    with mock_subprocess(subprocess_run), assert_no_chdir():
        repo.run_aggregate()
        repo.push_to_remote(target_branch="merge-branch-1234-master-abc12345")
    subprocess_run.assert_completed_calls()


def _mock_clean_github_responses(
    rsps, repo_name="edi", merged_prs=(773,), open_prs=(774, 663, 759)
):
    """Register GitHub API responses for the PRs of the default merges file."""
    for pull_id in merged_prs:
        rsps.add(
            responses.GET,
            f"https://api.github.com/repos/OCA/{repo_name}/pulls/{pull_id}",
            json={"state": "closed", "merged": True, "number": pull_id},
            status=200,
        )
    for pull_id in open_prs:
        rsps.add(
            responses.GET,
            f"https://api.github.com/repos/OCA/{repo_name}/pulls/{pull_id}",
            json={"state": "open", "merged": False, "number": pull_id},
            status=200,
        )


@pytest.mark.parametrize(("answer", "aggregated"), [("y", True), ("n", False)])
def test_cli_clean_prompts_for_aggregate(project, answer, aggregated):
    """Without an explicit --aggregate/--no-aggregate flag, `otools-pending
    clean` asks before re-aggregating each touched submodule."""
    mock_pending_merge_repo_paths("edi")
    repo = Repo("edi", path_check=False)
    with responses.RequestsMock() as rsps:
        _mock_clean_github_responses(rsps)
        with (
            mock.patch.object(pm_utils.Repo, "run_aggregate") as run_aggregate,
            mock.patch.object(pm_utils.Repo, "push_to_remote") as push_to_remote,
        ):
            result = project.invoke(
                pending.clean_pending,
                catch_exceptions=False,
                input=answer,
            )
    assert result.exit_code == 0
    assert "Re-aggregate" in result.output
    # The merged PR is removed regardless of the aggregation answer
    assert "OCA refs/pull/773/head" not in repo.merges_config()["merges"]
    assert run_aggregate.called is aggregated
    assert push_to_remote.called is aggregated


def test_cli_clean_prompts_for_aggregate_once_for_all_repos(project):
    """The re-aggregation question is asked once, listing every touched
    submodule, rather than once per submodule."""
    mock_pending_merge_repo_paths("edi")
    mock_pending_merge_repo_paths("web")
    with responses.RequestsMock() as rsps:
        _mock_clean_github_responses(rsps, repo_name="edi")
        _mock_clean_github_responses(rsps, repo_name="web")
        with (
            mock.patch.object(pm_utils.Repo, "run_aggregate") as run_aggregate,
            mock.patch.object(pm_utils.Repo, "push_to_remote") as push_to_remote,
        ):
            result = project.invoke(
                pending.clean_pending,
                catch_exceptions=False,
                input="y",
            )
    assert result.exit_code == 0
    assert result.output.count("Re-aggregate") == 1
    assert "Re-aggregate edi, web?" in result.output
    assert run_aggregate.call_count == 2
    assert push_to_remote.call_count == 2


@pytest.mark.parametrize(
    ("flag", "aggregated"), [("--aggregate", True), ("--no-aggregate", False)]
)
def test_cli_clean_explicit_aggregate_flag_skips_prompt(project, flag, aggregated):
    """An explicit --aggregate/--no-aggregate flag is honored without asking."""
    mock_pending_merge_repo_paths("edi")
    with responses.RequestsMock() as rsps:
        _mock_clean_github_responses(rsps)
        with (
            mock.patch.object(pm_utils.Repo, "run_aggregate") as run_aggregate,
            mock.patch.object(pm_utils.Repo, "push_to_remote") as push_to_remote,
        ):
            result = project.invoke(
                pending.clean_pending,
                [flag],
                catch_exceptions=False,
            )
    assert result.exit_code == 0
    assert "Re-aggregate" not in result.output
    assert run_aggregate.called is aggregated
    assert push_to_remote.called is aggregated


def _failing_aggregate(self, **kwargs):
    """Stand in for `Repo.run_aggregate`, failing on the `edi` submodule.

    A real failing command, so that its output has to reach the log without
    run_aggregate knowing anything about the capture.
    """
    if self.name == "edi":
        pm_utils.run(
            ["sh", "-c", "echo 'fatal: could not read from remote' >&2; exit 128"],
            check=True,
        )


def _reported_log(result, label):
    """Read back the log file the failure of ``label`` pointed at."""
    reported = re.search(rf"✖ {label} \(\d+s\): (\S*{label}\.log)", result.output)
    assert reported, f"No log file reported in:\n{result.output}"
    return Path(reported.group(1)).read_text()


def _run_clean_aggregating(project, run_aggregate=None):
    """Run `otools-pending clean --aggregate` over two touched submodules."""
    mock_pending_merge_repo_paths("edi")
    mock_pending_merge_repo_paths("web")

    with responses.RequestsMock() as rsps:
        _mock_clean_github_responses(rsps, repo_name="edi")
        _mock_clean_github_responses(rsps, repo_name="web")
        with (
            patch_attr(pm_utils.Repo, "run_aggregate", run_aggregate) as aggregate_mock,
            patch_attr(pm_utils.Repo, "push_to_remote") as push_mock,
            mock.patch.object(
                pending.gh, "get_target_branch", return_value="merge-branch-1234-master"
            ) as target_branch_mock,
        ):
            result = project.invoke(
                pending.clean_pending, ["--aggregate"], catch_exceptions=True
            )
    return SimpleNamespace(
        result=result,
        run_aggregate=aggregate_mock,
        push_to_remote=push_mock,
        get_target_branch=target_branch_mock,
    )


def test_cli_clean_aggregates_and_pushes_every_touched_submodule(project):
    run = _run_clean_aggregating(project)
    assert run.result.exit_code == 0
    assert run.run_aggregate.call_count == 2
    assert run.push_to_remote.call_count == 2
    for call in run.push_to_remote.call_args_list:
        assert call.kwargs["target_branch"] == "merge-branch-1234-master"


def test_cli_clean_resolves_the_target_branch_only_once(project):
    """Resolving it may prompt, which can't happen once the parallel
    aggregation started, and it's the same branch for every submodule."""
    run = _run_clean_aggregating(project)
    run.get_target_branch.assert_called_once()


def test_cli_clean_reports_failures_without_stopping(project):
    """One submodule failing to aggregate doesn't prevent the others, and its
    log file is pointed at for details."""
    run = _run_clean_aggregating(project, run_aggregate=_failing_aggregate)
    assert run.result.exit_code == 1
    # the healthy submodule was still aggregated and pushed
    assert [call.args[0].name for call in run.push_to_remote.call_args_list] == ["web"]
    # reported once, not once by the display and once again by a summary
    failed_lines = [
        line for line in run.result.output.splitlines() if line.startswith("✖")
    ]
    # the one submodule, and the step it was part of
    assert len(failed_lines) == 2
    assert failed_lines[1] == "✖ Aggregating submodules"
    assert "Please inspect the logs for details." in run.result.output
    # the failure points at its own log, and says nothing the log doesn't
    log = _reported_log(run.result, "edi")
    # the failing command's stderr reached the log, though run_aggregate was
    # never handed a sink: the capture is ambient
    assert "fatal: could not read from remote" in log
    # and so did the reason, which is no longer shown anywhere else
    assert "exit status 128" in log


def _capture_log_dirs(tmp_path):
    """Stand in for mkdtemp(), handing out a fresh directory per call.

    `clean` runs two steps, each with logs of its own, so one fixed directory
    would have the first step's cleanup pull it out from under the second.
    """
    made = []

    def mkdtemp(*args, **kwargs):
        path = tmp_path / f"logs{len(made)}"
        path.mkdir()
        made.append(path)
        return str(path)

    return made, mock.patch.object(pending.ui.tempfile, "mkdtemp", mkdtemp)


def test_cli_clean_discards_logs_when_all_went_fine(project, tmp_path):
    """Only --debug asks for them to be kept."""
    made, patched = _capture_log_dirs(tmp_path)
    with patched:
        run = _run_clean_aggregating(project)
    assert run.result.exit_code == 0
    # a directory per step, and not one of them left behind
    assert len(made) == 2
    assert not any(path.exists() for path in made)


def test_cli_clean_keeps_the_logs_in_debug_mode(project, tmp_path):
    """--debug keeps every log, successes included, and links them."""
    made, patched = _capture_log_dirs(tmp_path)
    # run_tasks decides for itself now, so that is where debug mode is read
    with patched, mock.patch.object(pending.ui, "is_debug", return_value=True):
        run = _run_clean_aggregating(project)
    assert run.result.exit_code == 0
    purging, aggregating = made
    # one log per pull request that was checked, and one per submodule aggregated
    assert sorted(path.name for path in purging.iterdir()) == [
        "OCA_edi_663.log",
        "OCA_edi_759.log",
        "OCA_edi_773.log",
        "OCA_edi_774.log",
        "OCA_web_663.log",
        "OCA_web_759.log",
        "OCA_web_773.log",
        "OCA_web_774.log",
    ]
    assert sorted(path.name for path in aggregating.iterdir()) == [
        "edi.log",
        "web.log",
    ]


# ── otools-pending aggregate ─────────────────────────────────────────────────


def _run_aggregate(project, args, run_aggregate=None):
    """Run `otools-pending aggregate` with the git operations mocked out."""
    with (
        patch_attr(pm_utils.Repo, "run_aggregate", run_aggregate) as aggregate_mock,
        patch_attr(pm_utils.Repo, "push_to_remote", None) as push_mock,
        mock.patch.object(
            pending.gh, "get_target_branch", return_value="branch-1234"
        ) as target_branch_mock,
    ):
        result = project.invoke(pending.aggregate, args, catch_exceptions=True)
    return SimpleNamespace(
        result=result,
        run_aggregate=aggregate_mock,
        push_to_remote=push_mock,
        get_target_branch=target_branch_mock,
    )


def test_cli_aggregate_runs_in_parallel(project):
    """Two submodules really are aggregated at the same time.

    The barrier only clears if both aggregations are in flight together, so a
    serial implementation would hang here rather than pass.
    """
    for name in ("edi", "web"):
        mock_pending_merge_repo_paths(name)
    both_in_flight = threading.Barrier(2, timeout=10)

    def run_aggregate(self, **kwargs):
        both_in_flight.wait()

    run = _run_aggregate(
        project, ["edi", "web", "--jobs", "2"], run_aggregate=run_aggregate
    )
    assert run.result.exit_code == 0


def test_cli_aggregate_jobs_caps_the_concurrency(project):
    """--jobs 1 serializes them: no two aggregations ever overlap."""
    for name in ("edi", "web", "stock"):
        mock_pending_merge_repo_paths(name)
    aggregate, state = peak_counter()
    run = _run_aggregate(
        project, ["edi", "web", "stock", "--jobs", "1"], run_aggregate=aggregate
    )
    assert run.result.exit_code == 0
    assert state["peak"] == 1


def test_cli_aggregate_resolves_the_target_branch_only_once(project):
    """It is the same branch for every submodule, and asking may prompt."""
    for name in ("edi", "web"):
        mock_pending_merge_repo_paths(name)
    run = _run_aggregate(project, ["edi", "web"])
    run.get_target_branch.assert_called_once()


def test_cli_aggregate_explicit_target_branch_is_not_resolved(project):
    mock_pending_merge_repo_paths("edi")
    run = _run_aggregate(project, ["edi", "--target-branch", "my-branch"])
    run.get_target_branch.assert_not_called()
    assert run.push_to_remote.call_args.kwargs["target_branch"] == "my-branch"


def test_cli_aggregate_no_push(project):
    mock_pending_merge_repo_paths("edi")
    run = _run_aggregate(project, ["edi", "--no-push"])
    assert run.result.exit_code == 0
    assert run.run_aggregate.called
    assert not run.push_to_remote.called
    # nothing is pushed, so there is no target branch to resolve (nor to confirm)
    run.get_target_branch.assert_not_called()


def test_cli_aggregate_reports_failures_without_stopping(project):
    """One submodule failing doesn't prevent the others, and its log is linked."""
    for name in ("edi", "web"):
        mock_pending_merge_repo_paths(name)
    run = _run_aggregate(project, ["edi", "web"], run_aggregate=_failing_aggregate)
    assert run.result.exit_code == 1
    assert [call.args[0].name for call in run.push_to_remote.call_args_list] == ["web"]
    assert "1 task(s) failed" in run.result.output
    assert "Please inspect the logs for details." in run.result.output
    # the failing command's stderr reached the log, though run_aggregate was
    # never handed a sink: the capture is ambient
    assert "fatal: could not read from remote" in _reported_log(run.result, "edi")


def test_cli_aggregate_requires_a_repo(project):
    result = project.invoke(pending.aggregate, [], catch_exceptions=True)
    assert result.exit_code != 0


def test_iter_pending_pull_requests(project):
    name = "edi"
    mock_pending_merge_repo_paths(
        name,
        tmpl=dedent(
            """
            ../{ext_src_rel_path}/{repo_name}:
                remotes:
                    camptocamp: git@github.com:camptocamp/{repo_name}.git
                    {org_name}: git@github.com:{org_name}/{repo_name}.git
                target: camptocamp merge-branch-{pid}-master
                merges:
                - {org_name} 14.0
                - {org_name} refs/pull/774/head
                - {org_name} refs/pull/773/head
                shell_command_after:
                - curl -sSL https://github.com/OCA/edi/pull/999.patch | git am -3 --keep-non-patch --exclude '*requirements.txt'
            """
        ),
    )
    repo = Repo(name)
    prs = list(repo._iter_pending_pull_requests())
    # 2 merges (the base ``OCA 14.0`` is skipped) + 1 patch
    assert len(prs) == 3
    pulls = [pr for pr in prs if not pr.is_patch]
    patches = [pr for pr in prs if pr.is_patch]
    assert sorted(pr.pr for pr in pulls) == [773, 774]
    assert [pr.pr for pr in patches] == [999]
    pr = pulls[0]
    assert pr._repo is repo
    assert pr.repo == "edi"
    assert pr.owner == "OCA"
    assert pr.shortcut.startswith("OCA/edi#")
    assert pr.url.startswith("https://github.com/OCA/edi/pull/")
    assert isinstance(pr, pm_utils.PendingPR)
    assert pr.is_enriched is False


@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_iter_pending_pull_requests_with_mismatched_github_repo(project):
    """The submodule directory name and the GitHub repo name don't always match.

    Real-world example: the ``src`` submodule (checked out under ``odoo/src``)
    pulls a base merge from ``OCA/OCB`` and patches from ``odoo/odoo`` —
    neither of those GitHub repos is named ``src``.
    """
    mock_pending_merge_repo_paths(
        "src",
        tmpl=dedent(
            """
            ../odoo/src:
              remotes:
                camptocamp: git@github.com:camptocamp/odoo.git
                oca: git@github.com:OCA/OCB.git
                odoo: git@github.com:odoo/odoo.git
              target: camptocamp merge-branch-{pid}-master
              merges:
              - oca 17.0
              - oca refs/pull/100/head
              shell_command_after:
              - curl -sSL https://github.com/odoo/odoo/pull/215486.patch | git am -3
            """
        ),
    )
    repo = Repo("src")
    prs = list(repo._iter_pending_pull_requests())
    assert len(prs) == 2
    merge_pr = next(pr for pr in prs if not pr.is_patch)
    patch_pr = next(pr for pr in prs if pr.is_patch)
    # Submodule directory is ``src``, but the GitHub repo is ``OCB``.
    assert merge_pr._repo.name == "src"
    assert merge_pr.owner == "OCA"
    assert merge_pr.repo == "OCB"
    assert merge_pr.shortcut == "OCA/OCB#100"
    assert merge_pr.url == "https://github.com/OCA/OCB/pull/100"
    # Patch entry resolves owner+repo from the patch URL itself.
    assert patch_pr.owner == "odoo"
    assert patch_pr.repo == "odoo"
    assert patch_pr.shortcut == "odoo/odoo#215486"
    assert patch_pr.url == "https://github.com/odoo/odoo/pull/215486"


def _fake_enrich(pr_states):
    """Build a side_effect that mutates a ``PendingPR`` in place.

    :param pr_states: mapping of PR number -> ``(state, merged)`` tuple.
    """

    def enrich(self):
        state, merged = pr_states.get(self.pr, ("open", False))
        self.state = state
        self.merged = merged
        self.title = f"PR {self.pr}"
        self.number = self.pr

    return enrich


def test_purge_merged_prs(project):
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name)
    pr_states = {
        774: ("open", False),
        773: ("closed", True),
        759: ("closed", False),
    }
    with mock.patch.object(
        pm_utils.PendingPR,
        "enrich_with_github",
        autospec=True,
        side_effect=_fake_enrich(pr_states),
    ):
        # Materialize within the patch context: ``purge_merged_prs`` is a
        # generator, so the API calls only happen as we iterate.
        purged = list(repo.purge_merged_prs())
    # Only the merged one is removed
    assert [pr.pr for pr in purged] == [773]
    remaining = repo.merges_config()["merges"]
    # base (OCA 14.0) + 774 + 663 + 759 stay; 773 is gone
    assert "OCA refs/pull/773/head" not in remaining
    assert "OCA refs/pull/774/head" in remaining
    assert "OCA refs/pull/759/head" in remaining


def test_purge_merged_prs_skips_unreachable(project, caplog):
    """A PR whose status can't be fetched is left in place (with a warning),
    and the failure doesn't abort purging the other PRs."""
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name)
    pr_states = {
        774: ("open", False),
        773: ("closed", True),
        759: ("closed", False),
    }
    enrich = _fake_enrich(pr_states)

    def enrich_or_fail(self):
        # PR 774 is unreachable (e.g. rate limited); the rest succeed.
        if self.pr == 774:
            raise requests.HTTPError("403 rate limit exceeded")
        enrich(self)

    with (
        mock.patch.object(
            pm_utils.PendingPR,
            "enrich_with_github",
            autospec=True,
            side_effect=enrich_or_fail,
        ),
        caplog.at_level("WARNING", logger="odoo_tools.utils.pending_merge"),
    ):
        purged = list(repo.purge_merged_prs())
    # The merged PR is still removed; the unreachable one is left alone.
    assert [pr.pr for pr in purged] == [773]
    remaining = repo.merges_config()["merges"]
    assert "OCA refs/pull/773/head" not in remaining
    assert "OCA refs/pull/774/head" in remaining
    assert "OCA refs/pull/759/head" in remaining
    # The failure is reported via a log warning.
    assert "OCA/edi#774" in caplog.text


def test_purge_merged_prs_with_comments(project):
    """Purging a merged PR drops its own preceding comment block and keeps the
    comment block of the still-pending PR that followed it."""
    name = "edi"
    tmpl = """
../{ext_src_rel_path}/{repo_name}:
  remotes:
    camptocamp: git@github.com:camptocamp/{repo_name}.git
    {org_name}: git@github.com:{org_name}/{repo_name}.git
  target: camptocamp merge-branch-{pid}-master
  merges:
  - {org_name} 19.0
  # [19.0][ADD] website_sale_stock_picking_policy
  # https://github.com/OCA/{repo_name}/pull/1195
  - {org_name} refs/pull/1195/head
  # [19.0][ADD] website_sale_product_multiple_qty
  # https://github.com/OCA/{repo_name}/pull/1172
  - {org_name} refs/pull/1172/head
"""
    mock_pending_merge_repo_paths(name, tmpl=tmpl)
    repo = Repo(name)
    # 1195 is merged, 1172 is still open.
    pr_states = {
        1195: ("closed", True),
        1172: ("open", False),
    }
    with mock.patch.object(
        pm_utils.PendingPR,
        "enrich_with_github",
        autospec=True,
        side_effect=_fake_enrich(pr_states),
    ):
        purged = list(repo.purge_merged_prs())
    # Only the merged one is removed
    assert [pr.pr for pr in purged] == [1195]
    # The 1195 line and its comment block are gone; the 1172 line keeps its own
    # comment block intact.
    expected = dedent(
        """\
        ../odoo/external-src/edi:
          remotes:
            camptocamp: git@github.com:camptocamp/edi.git
            OCA: git@github.com:OCA/edi.git
          target: camptocamp merge-branch-1234-master
          merges:
          - OCA 19.0
          # [19.0][ADD] website_sale_product_multiple_qty
          # https://github.com/OCA/edi/pull/1172
          - OCA refs/pull/1172/head
        """
    )
    assert repo.abs_merges_path.read_text() == expected


def _make_pending(repo, pr_id):
    return pm_utils.PendingPR(
        _repo=repo,
        owner="OCA",
        pr=pr_id,
        is_patch=False,
    )


def test_enrich_with_github(project):
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name)
    pending = _make_pending(repo, 773)
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/edi/pulls/773",
            json={
                "state": "closed",
                "merged": True,
                "number": 773,
                "title": "A merged PR",
                "updated_at": "2025-01-02T00:00:00Z",
                "labels": [{"name": "bug"}, {"name": "16.0"}],
            },
            status=200,
        )
        pending.enrich_with_github()
    assert pending.is_enriched
    assert pending.state == "closed"
    assert pending.merged is True
    assert pending.title == "A merged PR"
    assert pending.labels == ["bug", "16.0"]
    # Locally-derivable fields are unchanged
    assert pending._repo is repo
    assert pending.repo == "edi"
    assert pending.is_patch is False


def test_enrich_with_github_api_error(project):
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name)
    pending = _make_pending(repo, 9999)
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/edi/pulls/9999",
            status=403,
        )
        # The error is raised loudly; callers decide how to surface it.
        with pytest.raises(requests.HTTPError):
            pending.enrich_with_github()
    # State is left untouched (not enriched) so callers can flag the failure.
    assert not pending.is_enriched
    assert pending.state is None


def test_enrich_with_github_connection_error(project):
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name)
    pending = _make_pending(repo, 9999)
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/edi/pulls/9999",
            body=requests.ConnectionError("boom"),
        )
        with pytest.raises(requests.ConnectionError):
            pending.enrich_with_github()
    assert not pending.is_enriched
    assert pending.state is None


def test_enrich_with_github_uses_token(project, monkeypatch):
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name)
    pending = _make_pending(repo, 773)
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://api.github.com/repos/OCA/edi/pulls/773",
            json={"state": "open", "merged": False},
            status=200,
        )
        pending.enrich_with_github()
        sent = list(rsps.calls)
        assert sent[0].request.headers.get("Authorization") == "token secret-token"


# ── purge_repos, shared by `pending clean` and `submodule upgrade` ───────────


def test_purge_repos_enriches_every_pull_request_in_parallel(project):
    """One GitHub request per PR, and there are dozens, so they overlap.

    The barrier only clears if two are in flight together, so a serial
    implementation would time out on it rather than pass.
    """
    for name in ("edi", "web"):
        mock_pending_merge_repo_paths(name)
    repos = pending._resolve_repos(())
    expected = sum(len(list(repo._iter_pending_pull_requests())) for repo in repos)
    both_in_flight = threading.Barrier(2, timeout=10)
    cleared = []

    def enrich(self):
        # a serial run leaves the first one waiting until the barrier breaks,
        # and every later one raises immediately, so nothing is appended
        both_in_flight.wait()
        cleared.append(self.shortcut)

    with mock.patch.object(
        pm_utils.PendingPR, "enrich_with_github", autospec=True, side_effect=enrich
    ):
        pending.purge_repos(repos, jobs=2)
    # purge_repos records an enrichment failure rather than raising it, so the
    # count is what says the barrier really cleared
    assert len(cleared) == expected


def test_purge_repos_removes_the_merged_ones_and_keeps_the_rest(project):
    mock_pending_merge_repo_paths("edi")
    repos = pending._resolve_repos(())
    prs = list(repos[0]._iter_pending_pull_requests())
    merged = prs[0]

    def enrich(self):
        self.merged = self.shortcut == merged.shortcut
        self.state = "closed" if self.merged else "open"

    with mock.patch.object(
        pm_utils.PendingPR, "enrich_with_github", autospec=True, side_effect=enrich
    ):
        to_aggregate = pending.purge_repos(repos, jobs=2)
    # merges left, so the repo is worth re-aggregating rather than disposed of
    assert [repo.name for repo in to_aggregate] == ["edi"]
    left = [pr.shortcut for pr in repos[0]._iter_pending_pull_requests()]
    assert merged.shortcut not in left
    assert len(left) == len(prs) - 1


def test_purge_repos_does_nothing_without_pull_requests(project):
    assert pending.purge_repos([]) == []


def test_cli_clean_says_what_it_cleaned(project):
    """The purge announces itself above the pull requests it is working
    through, and settles on what came of it."""
    mock_pending_merge_repo_paths("edi")
    with responses.RequestsMock() as rsps:
        _mock_clean_github_responses(rsps)
        with (
            mock.patch.object(pm_utils.Repo, "run_aggregate"),
            mock.patch.object(pm_utils.Repo, "push_to_remote"),
        ):
            result = project.invoke(
                pending.clean_pending, ["--aggregate"], catch_exceptions=False
            )
    assert result.exit_code == 0
    assert "Cleaned 1 pending merge" in result.output
    # and the step that follows says what it is
    assert "Aggregating submodules" in result.output


def test_cli_clean_says_so_when_there_was_nothing_merged(project):
    """Nothing to clean is an outcome worth stating, not silence."""
    mock_pending_merge_repo_paths("edi")
    with responses.RequestsMock() as rsps:
        _mock_clean_github_responses(rsps, merged_prs=(), open_prs=(773, 774, 663, 759))
        result = project.invoke(pending.clean_pending, catch_exceptions=False)
    assert result.exit_code == 0
    assert "No merged pull request" in result.output


def test_purge_repos_writes_the_merges_file_from_several_threads(project):
    """Dropping a pull request is a read-modify-write of the whole document, so
    two at once on one submodule would lose one of the two edits."""
    mock_pending_merge_repo_paths("edi")
    repos = pending._resolve_repos(())
    prs = list(repos[0]._iter_pending_pull_requests())
    assert len(prs) > 2, "the fixture needs several PRs for this to mean anything"

    # all but the last are merged, so they are dropped at the same time -- and
    # one is left behind so the file is not disposed of before it can be read
    kept = prs[-1].shortcut

    def enrich(self):
        self.merged = self.shortcut != kept
        self.state = "open" if self.shortcut == kept else "closed"

    with mock.patch.object(
        pm_utils.PendingPR, "enrich_with_github", autospec=True, side_effect=enrich
    ):
        pending.purge_repos(repos, jobs=len(prs))
    # not one edit lost: every merged pull request is gone from the file
    assert [pr.shortcut for pr in repos[0]._iter_pending_pull_requests()] == [kept]


def test_cli_clean_says_what_became_of_each_pull_request(project):
    """The row a pull request is on is where its verdict is read."""
    mock_pending_merge_repo_paths("edi")
    with responses.RequestsMock() as rsps:
        _mock_clean_github_responses(rsps)
        with (
            mock.patch.object(pm_utils.Repo, "run_aggregate"),
            mock.patch.object(pm_utils.Repo, "push_to_remote"),
        ):
            result = project.invoke(
                pending.clean_pending, ["--aggregate"], catch_exceptions=False
            )
    assert "removed" in result.output
    assert "kept" in result.output


def test_purge_repos_shows_only_what_it_dropped(project):
    """A project has dozens of pending pull requests and most of them are still
    open; a screen full of "kept" buries the few that were dropped. So on a
    display only those are left, marked apart from an ordinary success.
    """
    mock_pending_merge_repo_paths("edi")
    repos = pending._resolve_repos(())
    prs = list(repos[0]._iter_pending_pull_requests())
    merged = prs[0]

    def enrich(self):
        self.merged = self.shortcut == merged.shortcut
        self.state = "closed" if self.merged else "open"

    console = terminal_console(width=90)
    with (
        mock.patch.object(
            pm_utils.PendingPR, "enrich_with_github", autospec=True, side_effect=enrich
        ),
        mock.patch.object(pending, "console", console),
        console.capture() as capture,
    ):
        pending.purge_repos(repos, jobs=2)
    frame = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", capture.get())
    assert f"● {merged.shortcut}" in frame
    assert "removed" in frame
    for pr in prs[1:]:
        assert pr.shortcut not in frame
    assert "kept" not in frame
