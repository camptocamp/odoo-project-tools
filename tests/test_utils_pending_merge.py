# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from pathlib import PosixPath

import pytest

from odoo_tools.config import get_conf_key
from odoo_tools.exceptions import PathNotFound
from odoo_tools.utils import pending_merge as pm_utils

from .common import fake_project_root, mock_pending_merge_repo_paths

Repo = pm_utils.Repo


# TODO: reuse everywhere
def compare_dict(a, b, keys=None):
    keys = keys or a.keys()
    for k in keys:
        assert a[k] == b[k], f"{k} does not match"


def test_repo_base():
    with fake_project_root():
        ext_rel_path = get_conf_key("ext_src_rel_path")
        pending_merge_rel_path = get_conf_key("pending_merge_rel_path")
        cwd = PosixPath(os.getcwd())
        repo = Repo("edi", path_check=False)
        expected = {
            "name": "edi",
            "company_git_remote": "camptocamp",
            "path": PosixPath(f"{ext_rel_path}/edi"),
            "abs_path": cwd / f"{ext_rel_path}/edi",
            "merges_path": PosixPath(f"{pending_merge_rel_path}/edi.yml"),
            "abs_merges_path": cwd / f"{pending_merge_rel_path}/edi.yml",
        }
        for k, v in expected.items():
            assert getattr(repo, k) == v, f"{k} does not match"


def test_repo_check_path():
    name = "edi"
    with fake_project_root():
        with pytest.raises(PathNotFound, match="GIT CONFIG*"):
            Repo(name)
        # Add fake git root
        mock_pending_merge_repo_paths(name, pending=False)
        with pytest.raises(PathNotFound, match="MERGES PATH*"):
            Repo(name)
        mock_pending_merge_repo_paths(name)
        assert Repo(name)


def test_repositories_from_pending_folder():
    names = sorted(["edi", "wms", "web-api"])
    with fake_project_root():
        for name in names:
            mock_pending_merge_repo_paths(name)
        repos = Repo.repositories_from_pending_folder()
        assert sorted([x.name for x in repos]) == names


def test_has_pending_merges():
    name = "edi"
    with fake_project_root():
        mock_pending_merge_repo_paths(name)
        repo = Repo(name)
        assert repo.has_pending_merges()


def test_merges_config():
    name = "edi"
    with fake_project_root():
        mock_pending_merge_repo_paths(name)
        repo = Repo(name)
        config = repo.merges_config()
        assert config["remotes"] == {
            "OCA": "git@github.com:OCA/edi.git",
            "camptocamp": "git@github.com:camptocamp/edi.git",
        }


# TODO: test all cases
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


# TODO: test all cases
@pytest.mark.usefixtures("all_template_versions")
@pytest.mark.project_setup(manifest=dict(odoo_version="16.0"))
def test_add_pending_pr_from_scratch():
    repo_name = "edi-framework"
    mock_pending_merge_repo_paths(repo_name, pending=False)
    repo = Repo(repo_name, path_check=False)
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


# TODO: test all cases
@pytest.mark.usefixtures("all_template_versions")
def test_add_pending_pr():
    name = "edi"
    mock_pending_merge_repo_paths(name)
    repo = Repo(name, path_check=False)
    repo.add_pending_pull_request("OCA", 778)
    expected = {
        "merges": [
            "OCA 14.0",
            "OCA refs/pull/778/head",
            "OCA refs/pull/774/head",
            "OCA refs/pull/773/head",
            "OCA refs/pull/663/head",
            "OCA refs/pull/759/head",
        ],
        "remotes": {
            "OCA": "git@github.com:OCA/edi.git",
            "camptocamp": "git@github.com:camptocamp/edi.git",
        },
        "target": "camptocamp merge-branch-1234-master",
    }
    compare_dict(repo.merges_config(), expected)


# TODO: test all cases
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


# TODO: test all cases
def __test_add_pending_commit_from_scratch():
    name = "edi"
    with fake_project_root(manifest=dict(odoo_version="16.0")):
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


# TODO: test all cases
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
            "git am \"$(git format-patch -1 a86f5fe73e1f34f29cb2ad0dca253e47ce625406 -o ../patches)\"",
        ],
    }
    compare_dict(repo.merges_config(), expected)


# TODO: test all cases
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


# TODO: test all cases
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
        "git am \"$(git format-patch -1 a86f5fe73e1f34f29cb2ad0dca253e47ce625406 -o ../patches)\"",
    ]
    repo.remove_pending_commit("OCA", sha)
    shell_command_after = repo.merges_config().get("shell_command_after", [])
    expected = []
    assert shell_command_after == expected


# TODO: test all cases
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
