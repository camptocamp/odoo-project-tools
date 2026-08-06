from pathlib import Path
from unittest import mock

import pytest

from odoo_tools.cli import submodule

from .common import MockSubprocessRun, get_fixture_path, mock_pending_merge_repo_paths


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_init(project):
    odoo_version = "16.0"
    mock_fn = MockSubprocessRun(
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
    mock_fn = MockSubprocessRun([])
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
    mock_fn = MockSubprocessRun(
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
)
def test_sync_remote_no_pending_merges(project):
    """A submodule without a pending-merges file is checked out on the version."""
    new_remote_url = "git@github.com:OCA/some-repo.git"
    mock_pending_merge_repo_paths("some-repo", src=True, pending=False)
    mock_fn = MockSubprocessRun(
        [
            # set_remote_url -> submodule_set_url
            {
                "args": lambda args: (
                    args[:2] == ["git", "config"] and args[-1] == new_remote_url
                ),
            },
            # set_remote_url -> git remote set-url
            {
                "args": ["git", "remote", "set-url", "origin", new_remote_url],
            },
            # checkout -> git fetch
            {
                "args": ["git", "fetch", "origin", "16.0"],
            },
            # checkout -> git checkout
            {
                "args": ["git", "checkout", "origin/16.0"],
            },
        ]
    )
    with (
        mock.patch("subprocess.run", mock_fn),
        mock.patch.object(
            submodule.pm_utils, "get_new_remote_url", return_value=new_remote_url
        ),
        mock.patch.object(submodule.ui, "ask_confirmation", return_value=True),
    ):
        result = project.invoke(
            submodule.sync_remote,
            ["odoo/external-src/some-repo"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_fn.assert_completed_calls()
    assert f"is now being sourced from {new_remote_url}" in result.output


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
)
def test_sync_remote_with_pending_merges(project):
    new_remote_url = "git@github.com:camptocamp/some-repo.git"
    mock_pending_merge_repo_paths("some-repo", src=True, pending=True)
    mock_fn = MockSubprocessRun(
        [
            # set_remote_url -> submodule_set_url
            {
                "args": lambda args: (
                    args[:2] == ["git", "config"] and args[-1] == new_remote_url
                ),
            },
            # set_remote_url -> git remote set-url
            {
                "args": ["git", "remote", "set-url", "origin", new_remote_url],
            },
        ]
    )
    with (
        mock.patch("subprocess.run", mock_fn),
        mock.patch.object(
            submodule.pm_utils, "get_new_remote_url", return_value=new_remote_url
        ),
        mock.patch.object(submodule.ui, "ask_confirmation", return_value=True),
        mock.patch.object(
            submodule.pm_utils.Repo, "rebuild_consolidation_branch"
        ) as mock_rebuild,
    ):
        result = project.invoke(
            submodule.sync_remote,
            ["odoo/external-src/some-repo"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_fn.assert_completed_calls()
    mock_rebuild.assert_called_once_with(push=True)


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
        "/odoo/local-src, " + "\\",
        "/odoo/odoo/external-src/account-closing, \\",
        '/odoo/odoo/external-src/account-financial-reporting" \\',
        "",
    ]


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    proj_tmpl_ver=2,
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_ls_dockerfile_v2(project):
    result = project.invoke(
        submodule.ls,
        ["--dockerfile"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        'ENV ADDONS_PATH="/src/odoo/odoo/addons, \\',
        "/src/odoo/addons, " + "\\",
        "/src/enterprise, " + "\\",
        "/odoo/addons, " + "\\",
        "/odoo/odoo/external-src/account-closing, " + "\\",
        '/odoo/odoo/external-src/account-financial-reporting" \\',
        "",
    ]


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
        "odoo/paid-modules/.gitkeep": "",
    },
)
def test_ls_dockerfile_with_paid_modules(project):
    result = project.invoke(
        submodule.ls,
        ["--dockerfile"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        'ENV ADDONS_PATH="/odoo/src/odoo/odoo/addons, \\',
        "/odoo/src/odoo/addons, " + "\\",
        "/odoo/local-src, " + "\\",
        "/odoo/odoo/external-src/account-closing, " + "\\",
        "/odoo/odoo/external-src/account-financial-reporting, " + "\\",
        '/odoo/paid-modules" \\',
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
    mock_fn = MockSubprocessRun(
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
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_any_pr_left",
            return_value=True,
        ),
        mock.patch.object(
            submodule.pm_utils.Repo, "purge_merged_prs", return_value=[]
        ) as mock_purge,
        mock.patch.object(
            submodule.pm_utils.Repo, "rebuild_consolidation_branch"
        ) as mock_rebuild,
        mock.patch.object(
            submodule.pm_utils.gh, "get_target_branch", return_value="merge-branch"
        ),
    ):
        result = project.invoke(
            submodule.upgrade,
            ["odoo/external-src/account-closing"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_purge.assert_called_once_with()
    mock_rebuild.assert_called_once_with(push=True, target_branch="merge-branch")


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_upgrade_pending_merges_target_branch_resolved_once(project):
    # The target branch depends on the project and its HEAD only, so it must be
    # resolved once and reused, otherwise get_target_branch() asks to confirm
    # the override once per submodule with pending merges.
    with (
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            return_value=True,
        ),
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_any_pr_left",
            return_value=True,
        ),
        mock.patch.object(submodule.pm_utils.Repo, "purge_merged_prs", return_value=[]),
        mock.patch.object(
            submodule.pm_utils.Repo, "rebuild_consolidation_branch"
        ) as mock_rebuild,
        mock.patch.object(
            submodule.pm_utils.gh, "get_target_branch", return_value="merge-branch"
        ) as mock_get_target_branch,
    ):
        result = project.invoke(
            submodule.upgrade,
            [],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_get_target_branch.assert_called_once_with()
    # The fixture has 2 submodules: both are re-aggregated with the same branch.
    assert mock_rebuild.call_args_list == [
        mock.call(push=True, target_branch="merge-branch"),
        mock.call(push=True, target_branch="merge-branch"),
    ]


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_upgrade_no_aggregate_never_resolves_target_branch(project):
    # Nothing gets re-aggregated: the target branch must never be resolved, so
    # that such a run never asks to confirm a branch override.
    with (
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            return_value=True,
        ),
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_any_pr_left",
            return_value=True,
        ),
        mock.patch.object(submodule.pm_utils.Repo, "purge_merged_prs", return_value=[]),
        mock.patch.object(
            submodule.pm_utils.gh, "get_target_branch"
        ) as mock_get_target_branch,
    ):
        result = project.invoke(
            submodule.upgrade,
            ["--no-aggregate"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_get_target_branch.assert_not_called()


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
@pytest.mark.parametrize(
    "options,expect_purge,expect_rebuild",
    [
        # re-aggregates without cleaning the pending merges
        (["--no-clean-pending"], False, True),
        # cleans the pending merges without re-aggregating
        (["--no-aggregate"], True, False),
        # completely ignores submodules with pending merges
        (["--no-clean-pending", "--no-aggregate"], False, False),
    ],
)
def test_upgrade_pending_merges_options(project, options, expect_purge, expect_rebuild):
    with (
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            return_value=True,
        ),
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_any_pr_left",
            return_value=True,
        ),
        mock.patch.object(
            submodule.pm_utils.Repo, "purge_merged_prs", return_value=[]
        ) as mock_purge,
        mock.patch.object(
            submodule.pm_utils.Repo, "rebuild_consolidation_branch"
        ) as mock_rebuild,
        mock.patch.object(
            submodule.pm_utils.gh, "get_target_branch", return_value="merge-branch"
        ),
        mock.patch.object(submodule.git, "submodule_update") as mock_update,
        mock.patch.object(submodule.git, "submodule_upgrade") as mock_upgrade,
    ):
        result = project.invoke(
            submodule.upgrade,
            ["odoo/external-src/account-closing", *options],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    assert mock_purge.called is expect_purge
    assert mock_rebuild.called is expect_rebuild
    # The submodule still has pending merges: it's never upgraded from remote.
    mock_update.assert_not_called()
    mock_upgrade.assert_not_called()
    if not expect_rebuild:
        assert "Skipping odoo/external-src/account-closing" in result.output


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_upgrade_pending_merges_all_purged(project):
    # Regression test for #252: when purging removes the last pending PR,
    # purge_merged_prs() already deletes the pending-merges file. The upgrade
    # command must NOT call _handle_empty_merges_file() again, otherwise it
    # reads the now-deleted file and crashes with FileNotFoundError.
    # True the first time (enter purge branch), False afterwards because
    # purge_merged_prs() deleted the now-empty pending-merges file.
    pending_merges = iter([True])

    def fake_has_pending_merges(self):
        return next(pending_merges, False)

    with (
        mock.patch.object(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            autospec=True,
            side_effect=fake_has_pending_merges,
        ),
        mock.patch.object(
            submodule.pm_utils.Repo, "purge_merged_prs", return_value=[]
        ) as mock_purge,
        mock.patch.object(
            submodule.pm_utils.Repo, "_handle_empty_merges_file"
        ) as mock_handle,
        mock.patch.object(submodule.git, "submodule_update"),
        mock.patch.object(submodule.git, "submodule_upgrade"),
    ):
        result = project.invoke(
            submodule.upgrade,
            ["odoo/external-src/account-closing"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_purge.assert_called_once_with()
    # The caller must not re-handle the empty file; purge_merged_prs() owns it.
    mock_handle.assert_not_called()


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
    mock_fn = MockSubprocessRun(
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
