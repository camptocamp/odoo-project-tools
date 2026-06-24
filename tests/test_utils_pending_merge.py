# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path
from textwrap import dedent
from unittest import mock

import pytest
import responses
from git.config import GitConfigParser

from odoo_tools.exceptions import Exit, PathNotFound
from odoo_tools.utils import pending_merge as pm_utils
from odoo_tools.utils.config import config

from .common import mock_pending_merge_repo_paths

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
    pm_utils.add_pending(
        "https://github.com/OCA/edi/pull/1470.patch",
        aggregate=False,
    )
    pm_utils.add_pending(
        "https://github.com/OCA/edi/pull/1471",
        patch=True,
        aggregate=False,
    )
    shell_command_after = repo.merges_config().get("shell_command_after", [])
    line_tmpl = "curl -sSL https://github.com/OCA/edi/pull/{}.patch | git am -3 --keep-non-patch --exclude '*requirements.txt'"
    for pid in (1470, 1471):
        assert line_tmpl.format(pid) in shell_command_after, shell_command_after


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
            status=404,
        )
        pending.enrich_with_github()
    # Empty state on API failure means purge_merged_prs won't touch it
    assert pending.is_enriched
    assert pending.state == ""
    assert pending.merged is False


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
