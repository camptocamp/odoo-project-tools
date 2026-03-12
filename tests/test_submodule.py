from pathlib import Path
from unittest import mock

import pytest

from odoo_tools.cli import submodule

from .common import get_fixture_path, mock_pending_merge_repo_paths, mock_subprocess_run


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_init(project):
    odoo_version = "16.0"
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "git",
                    "autoshare-submodule-add",
                    "-b",
                    odoo_version,
                    "--force",
                    "git@github.com:OCA/account-closing.git",
                    "odoo/external-src/account-closing",
                ],
            },
            {
                "args": [
                    "git",
                    "autoshare-submodule-add",
                    "-b",
                    odoo_version,
                    "--force",
                    "git@github.com:OCA/account-financial-reporting.git",
                    "odoo/external-src/account-financial-reporting",
                ],
            },
        ]
    )
    with mock.patch("subprocess.run", mock_fn):
        result = project.invoke(
            submodule.init,
            [],
            catch_exceptions=False,
        )
    mock_fn.assert_completed_calls()
    assert result.exit_code == 0


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
)
def test_init_missing_gitmodules(project):
    mock_fn = mock_subprocess_run([])
    with mock.patch("subprocess.run", mock_fn):
        result = project.invoke(
            submodule.init,
            [],
            catch_exceptions=False,
        )
    mock_fn.assert_completed_calls()
    assert result.exit_code == 0


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_update(project):
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "git",
                    "submodule",
                    "sync",
                    "--",
                    "odoo/external-src/account-closing",
                ],
            },
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "odoo/external-src/account-closing",
                ],
            },
            {
                "args": [
                    "git",
                    "submodule",
                    "sync",
                    "--",
                    "odoo/external-src/account-financial-reporting",
                ],
            },
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "odoo/external-src/account-financial-reporting",
                ],
            },
        ]
    )
    with (
        mock.patch("subprocess.run", mock_fn),
        mock.patch(
            "odoo_tools.utils.git.find_autoshare_repository", return_value=(None, None)
        ),
    ):
        result = project.invoke(
            submodule.update,
            [],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_fn.assert_completed_calls()


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_ls(project):
    result = project.invoke(
        submodule.ls,
        ["--no-dockerfile"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "odoo/external-src/account-closing",
        "odoo/external-src/account-financial-reporting",
    ]


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
)
def test_push(project):
    mock_pending_merge_repo_paths("some-repo", src=True, pending=True)
    with mock.patch.object(
        submodule.pm_utils.Repo, "push_to_remote"
    ) as mock_push_to_remote:
        result = project.invoke(
            submodule.push,
            ["some-repo", "--target-branch", "my-target-branch"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_push_to_remote.assert_called_once_with(target_branch="my-target-branch")
    assert "my-target-branch" in result.output
    assert "Done." in result.output


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_ls_dockerfile(project):
    result = project.invoke(
        submodule.ls,
        ["--dockerfile"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        'ENV ADDONS_PATH="/odoo/src/odoo/odoo/addons, \\',
        "/odoo/src/odoo/addons, \\",
        "/odoo/src/enterprise, \\",
        "/odoo/odoo/addons, \\",
        "/odoo/odoo/external-src/account-closing, \\",
        "/odoo/odoo/external-src/account-financial-reporting, \\",
        '/odoo/odoo/paid-modules" \\',
        "",
    ]


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_upgrade_no_pending_merges(project):
    commit_before = "aaa111"
    commit_after = "bbb222"
    mock_fn = mock_subprocess_run(
        [
            # submodule_update for account-closing
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "odoo/external-src/account-closing",
                ],
            },
            # get_submodule_commit before (submodule_upgrade)
            {
                "args": lambda args: (
                    args[:2] == ["git", "-C"] and args[-2:] == ["rev-parse", "HEAD"]
                ),
                "stdout": commit_before.encode(),
            },
            # submodule_upgrade (no branch)
            {
                "args": lambda args: (
                    args[:5]
                    == [
                        "git",
                        "submodule",
                        "update",
                        "-f",
                        "--remote",
                    ]
                    and "odoo/external-src/account-closing" in args
                ),
            },
            # get_submodule_commit after
            {
                "args": lambda args: (
                    args[:2] == ["git", "-C"] and args[-2:] == ["rev-parse", "HEAD"]
                ),
                "stdout": commit_after.encode(),
            },
            # submodule_update for account-financial-reporting
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "odoo/external-src/account-financial-reporting",
                ],
            },
            # get_submodule_commit before
            {
                "args": lambda args: (
                    args[:2] == ["git", "-C"] and args[-2:] == ["rev-parse", "HEAD"]
                ),
                "stdout": commit_after.encode(),
            },
            # submodule_upgrade (no branch)
            {
                "args": lambda args: (
                    args[:5]
                    == [
                        "git",
                        "submodule",
                        "update",
                        "-f",
                        "--remote",
                    ]
                    and "odoo/external-src/account-financial-reporting" in args
                ),
            },
            # get_submodule_commit after (same = not upgraded)
            {
                "args": lambda args: (
                    args[:2] == ["git", "-C"] and args[-2:] == ["rev-parse", "HEAD"]
                ),
                "stdout": commit_after.encode(),
            },
        ]
    )
    with (
        mock.patch("subprocess.run", mock_fn),
        mock.patch(
            "odoo_tools.utils.git.find_autoshare_repository",
            return_value=(None, None),
        ),
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            return_value=False,
        ),
    ):
        result = project.invoke(
            submodule.upgrade,
            [],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_fn.assert_completed_calls()
    assert "UPGRADED" in result.output
    assert "NOT UPGRADED" in result.output


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_upgrade_with_pending_merges(project):
    with (
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            return_value=True,
        ),
        mock.patch.object(submodule.pm_utils.Repo, "show_prs") as mock_show_prs,
        mock.patch.object(
            submodule.pm_utils.Repo, "rebuild_consolidation_branch"
        ) as mock_rebuild,
    ):
        result = project.invoke(
            submodule.upgrade,
            ["odoo/external-src/account-closing"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_show_prs.assert_called_once_with(purge="merged", yes_all=True)
    mock_rebuild.assert_called_once_with(push=True)


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_upgrade_force_branch(project):
    commit_before = "aaa111"
    commit_after = "bbb222"
    mock_fn = mock_subprocess_run(
        [
            # submodule_update
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "odoo/external-src/account-closing",
                ],
            },
            # get_submodule_commit before
            {
                "args": lambda args: (
                    args[:2] == ["git", "-C"] and args[-2:] == ["rev-parse", "HEAD"]
                ),
                "stdout": commit_before.encode(),
            },
            # git reset
            {
                "args": lambda args: args[:2] == ["git", "-C"] and args[-1] == "--hard",
            },
            # git fetch
            {
                "args": lambda args: args[:2] == ["git", "-C"] and "fetch" in args,
            },
            # git checkout
            {
                "args": lambda args: (
                    args[:2] == ["git", "-C"] and "checkout" in args and "17.0" in args
                ),
            },
            # get_submodule_commit after
            {
                "args": lambda args: (
                    args[:2] == ["git", "-C"] and args[-2:] == ["rev-parse", "HEAD"]
                ),
                "stdout": commit_after.encode(),
            },
        ]
    )
    with (
        mock.patch("subprocess.run", mock_fn),
        mock.patch(
            "odoo_tools.utils.git.find_autoshare_repository",
            return_value=(None, None),
        ),
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            return_value=False,
        ),
    ):
        result = project.invoke(
            submodule.upgrade,
            [
                "odoo/external-src/account-closing",
                "--force-branch",
                "17.0",
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_fn.assert_completed_calls()
    assert "UPGRADED" in result.output
