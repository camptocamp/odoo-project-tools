import threading
import time
from pathlib import Path
from unittest import mock

import pytest
from rich.console import Console

from odoo_tools.cli import submodule
from odoo_tools.utils import os_exec, ui

from .common import (
    MockSubprocessRun,
    assert_no_chdir,
    get_fixture_path,
    mock_pending_merge_repo_paths,
    mock_subprocess,
    patch_attr,
    peak_counter,
    with_submodules,
)


@with_submodules
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
    # --jobs 1 so that the submodules are handled in .gitmodules order and the
    # spec above stays an assertion about what runs rather than a race.
    with mock_subprocess(mock_fn), assert_no_chdir():
        result = project.invoke(
            submodule.init,
            ["--jobs", "1"],
            catch_exceptions=False,
        )
    mock_fn.assert_completed_calls()
    assert result.exit_code == 0
    assert "Submodules initialized." in result.output
    assert "ENV ADDONS_PATH" in result.output


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
)
def test_init_missing_gitmodules(project):
    mock_fn = MockSubprocessRun([])
    with mock_subprocess(mock_fn):
        result = project.invoke(
            submodule.init,
            [],
            catch_exceptions=False,
        )
    mock_fn.assert_completed_calls()
    assert result.exit_code == 0
    # nothing to do is not a failure, and the addons-path is still worth having
    assert "Submodules initialized." in result.output
    assert "ENV ADDONS_PATH" in result.output


#: `git submodule status` marks each submodule with its relationship to the
#: commit the superproject records: "+" a different commit, "-" not
#: initialized, " " aligned, "U" conflicted. Only the first two are updated.
MOCKED_GIT_SUBMODULE_STATUS = {
    "args": ["git", "submodule", "status"],
    "stdout": (
        b"+111 odoo/external-src/account-closing\n"
        b" 222 odoo/external-src/account-financial-reporting\n"
    ),
}
CLOSING = "odoo/external-src/account-closing"
REPORTING = "odoo/external-src/account-financial-reporting"


def mocked_submodule_batch(*paths):
    """The superproject's own bookkeeping, done once for the whole set."""
    return [
        {"args": ["git", "submodule", "sync", "--", *paths]},
        {"args": ["git", "submodule", "init", "--", *paths]},
    ]


def mocked_submodule_update(path):
    """One submodule's own update -- the part that runs in parallel."""
    return {"args": ["git", "submodule", "update", "--", path]}


def _invoke_update(project, mock_fn, args):
    # --jobs 1 so that the submodules are handled in .gitmodules order and the
    # spec stays an assertion about what runs rather than a race.
    with (
        mock_subprocess(mock_fn),
        mock.patch(
            "odoo_tools.utils.git.find_autoshare_repository", return_value=(None, None)
        ),
        assert_no_chdir(),
    ):
        result = project.invoke(
            submodule.update, [*args, "--jobs", "1"], catch_exceptions=False
        )
    assert result.exit_code == 0
    return result


@with_submodules
def test_update_only_touches_the_out_of_sync_ones(project):
    """`git submodule update --init` is run as its two documented halves, so
    that only the one writing the superproject's config has to be serialised --
    and only the submodules that are actually behind get either."""
    mock_fn = MockSubprocessRun(
        [
            MOCKED_GIT_SUBMODULE_STATUS,
            *mocked_submodule_batch(CLOSING),
            mocked_submodule_update(CLOSING),
        ]
    )
    _invoke_update(project, mock_fn, [])
    mock_fn.assert_completed_calls()


@with_submodules
def test_update_submodule_path(project):
    mock_fn = MockSubprocessRun(
        [
            MOCKED_GIT_SUBMODULE_STATUS,
            *mocked_submodule_batch(CLOSING),
            mocked_submodule_update(CLOSING),
        ]
    )
    _invoke_update(project, mock_fn, [CLOSING])
    mock_fn.assert_completed_calls()


@with_submodules
def test_update_aligned_submodule_path_does_nothing(project):
    """Naming a submodule that is already at the recorded commit is not a way
    round the check -- and with nothing to do, no display is drawn either."""
    mock_fn = MockSubprocessRun([MOCKED_GIT_SUBMODULE_STATUS])
    _invoke_update(project, mock_fn, [REPORTING])
    mock_fn.assert_completed_calls()


@with_submodules
def test_update_force_skips_the_status_check(project):
    """With --force the statuses are not consulted at all, and both submodules
    go through the batched bookkeeping together."""
    paths = [CLOSING, REPORTING]
    mock_fn = MockSubprocessRun(
        [
            *mocked_submodule_batch(*paths),
            *(mocked_submodule_update(path) for path in paths),
        ]
    )
    _invoke_update(project, mock_fn, ["--force"])
    mock_fn.assert_completed_calls()


@with_submodules
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
        mock_subprocess(mock_fn),
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
        mock_subprocess(mock_fn),
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


@with_submodules
def test_ls_dockerfile(project):
    result = project.invoke(
        submodule.ls,
        ["--dockerfile"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        'ENV ADDONS_PATH="/odoo/src/odoo/addons, \\',
        "/odoo/src/addons, \\",
        "/odoo/local-src, \\",
        "/odoo/external-src/account-closing, \\",
        '/odoo/external-src/account-financial-reporting" \\',
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
        "/src/odoo/addons, \\",
        "/src/enterprise, \\",
        "/odoo/addons, \\",
        "/odoo/external-src/account-closing, \\",
        '/odoo/external-src/account-financial-reporting" \\',
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
        'ENV ADDONS_PATH="/odoo/src/odoo/addons, \\',
        "/odoo/src/addons, \\",
        "/odoo/local-src, \\",
        "/odoo/external-src/account-closing, \\",
        "/odoo/external-src/account-financial-reporting, \\",
        '/odoo/paid-modules" \\',
        "",
    ]


@with_submodules
def test_upgrade_no_pending_merges(project):
    commit_before = "aaa111"
    commit_after = "bbb222"
    mock_fn = MockSubprocessRun(
        [
            # the superproject bookkeeping, once for every submodule being
            # upgraded: `.gitmodules` is the source of truth for the url
            {"args": lambda args: args[:3] == ["git", "submodule", "sync"]},
            {"args": lambda args: args[:3] == ["git", "submodule", "init"]},
            # submodule_update for account-closing
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--",
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
            # submodule_upgrade: fetch the branch by url, check out what came
            # back -- no guessing which local remote holds the tip
            {"args": lambda args: args[3:5] == ["reset", "--hard"]},
            {"args": lambda args: args[3] == "fetch" and args[-1] == "16.0"},
            {"args": lambda args: args[3:] == ["checkout", "--detach", "FETCH_HEAD"]},
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
                    "--",
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
            # submodule_upgrade: fetch the branch by url, check out what came
            # back -- no guessing which local remote holds the tip
            {"args": lambda args: args[3:5] == ["reset", "--hard"]},
            {"args": lambda args: args[3] == "fetch" and args[-1] == "16.0"},
            {"args": lambda args: args[3:] == ["checkout", "--detach", "FETCH_HEAD"]},
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
        mock_subprocess(mock_fn),
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
            ["--jobs", "1"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_fn.assert_completed_calls()
    assert "UPGRADED" in result.output
    assert "NOT UPGRADED" in result.output


@with_submodules
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
        mock.patch.object(submodule.pending, "purge_repos") as mock_purge,
        mock.patch.object(
            submodule.pm_utils.Repo, "rebuild_consolidation_branch"
        ) as mock_rebuild,
        mock.patch.object(
            submodule.gh, "get_target_branch", return_value="merge-branch"
        ),
    ):
        result = project.invoke(
            submodule.upgrade,
            ["odoo/external-src/account-closing", "--jobs", "1"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_purge.assert_called_once()
    assert [repo.name for repo in mock_purge.call_args.args[0]] == ["account-closing"]
    mock_rebuild.assert_called_once_with(push=True, target_branch="merge-branch")


@with_submodules
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
        mock.patch.object(submodule.pending, "purge_repos"),
        mock.patch.object(submodule.gh, "get_target_branch") as mock_get_target_branch,
    ):
        result = project.invoke(
            submodule.upgrade,
            ["--no-aggregate", "--jobs", "1"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_get_target_branch.assert_not_called()


@with_submodules
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
        mock.patch.object(submodule.pending, "purge_repos") as mock_purge,
        mock.patch.object(
            submodule.pm_utils.Repo, "rebuild_consolidation_branch"
        ) as mock_rebuild,
        mock.patch.object(
            submodule.gh, "get_target_branch", return_value="merge-branch"
        ),
        mock.patch.object(submodule.git, "submodule_update") as mock_update,
        mock.patch.object(submodule.git, "submodule_upgrade") as mock_upgrade,
    ):
        result = project.invoke(
            submodule.upgrade,
            ["odoo/external-src/account-closing", "--jobs", "1", *options],
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


@with_submodules
def test_upgrade_pending_merges_all_purged(project):
    # Regression test for #252: purging can remove the last pending PR, and
    # `pending.purge_repos` disposes of the emptied merges file itself. The
    # upgrade command must NOT handle it again, or it reads a file that is no
    # longer there and crashes with FileNotFoundError.
    # True the first time (so the repo is purged), False afterwards because the
    # purge deleted the now-empty pending-merges file.
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
        mock.patch.object(submodule.pending, "purge_repos") as mock_purge,
        mock.patch.object(
            submodule.pm_utils.Repo, "_handle_empty_merges_file"
        ) as mock_handle,
        mock.patch.object(submodule.git, "sync_submodules"),
        mock.patch.object(submodule.git, "register_submodules"),
        mock.patch.object(submodule.git, "submodule_update"),
        mock.patch.object(submodule.git, "submodule_upgrade"),
    ):
        result = project.invoke(
            submodule.upgrade,
            ["odoo/external-src/account-closing", "--jobs", "1"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_purge.assert_called_once()
    # The caller must not re-handle the empty file; purge_repos() owns it.
    mock_handle.assert_not_called()


@with_submodules
def test_upgrade_force_branch(project):
    commit_before = "aaa111"
    commit_after = "bbb222"
    mock_fn = MockSubprocessRun(
        [
            # the superproject bookkeeping, once for every submodule being
            # upgraded: `.gitmodules` is the source of truth for the url
            {"args": lambda args: args[:3] == ["git", "submodule", "sync"]},
            {"args": lambda args: args[:3] == ["git", "submodule", "init"]},
            # submodule_update
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--",
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
            # submodule_upgrade: fetch the forced branch by url, then check
            # out exactly what came back
            {"args": lambda args: args[3:5] == ["reset", "--hard"]},
            {"args": lambda args: args[3] == "fetch" and args[-1] == "17.0"},
            {"args": lambda args: args[3:] == ["checkout", "--detach", "FETCH_HEAD"]},
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
        mock_subprocess(mock_fn),
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
                "--jobs",
                "1",
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_fn.assert_completed_calls()
    assert "UPGRADED" in result.output


# ── init / update, several submodules at a time ──────────────────────────────

SUBMODULES = [
    "odoo/external-src/account-closing",
    "odoo/external-src/account-financial-reporting",
]


def _patch_git(name, replacement=None):
    """Replace a git helper with a recording mock, optionally acting as one."""
    return mock.patch.object(submodule.git, name, side_effect=replacement)


@with_submodules
def test_update_runs_the_submodules_in_parallel(project):
    """Both submodules really are updated at the same time.

    The barrier only clears if both are in flight together, so a serial
    implementation times out on it rather than passing.
    """
    both_in_flight = threading.Barrier(2, timeout=10)

    with (
        _patch_git("sync_submodules"),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update", lambda *a, **kw: both_in_flight.wait()),
    ):
        result = project.invoke(
            submodule.update, ["--force", "--jobs", "2"], catch_exceptions=True
        )
    assert result.exit_code == 0, result.output


@with_submodules
def test_init_runs_the_submodules_in_parallel(project):
    both_in_flight = threading.Barrier(2, timeout=10)

    with _patch_git("submodule_init", lambda *a, **kw: both_in_flight.wait()):
        result = project.invoke(submodule.init, ["--jobs", "2"], catch_exceptions=True)
    assert result.exit_code == 0, result.output


@with_submodules
def test_update_jobs_caps_the_concurrency(project):
    """--jobs 1 serialises them: no two updates ever overlap."""
    update, state = peak_counter()
    with (
        _patch_git("sync_submodules"),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update", update),
    ):
        result = project.invoke(
            submodule.update, ["--force", "--jobs", "1"], catch_exceptions=True
        )
    assert result.exit_code == 0
    assert state["peak"] == 1


def _fails_on_account_closing(path, *args, **kwargs):
    if str(path) == SUBMODULES[0]:
        raise RuntimeError("fatal: could not read from remote")


@with_submodules
def test_update_reports_failures_without_stopping(project):
    """One submodule failing doesn't prevent the others, and its log is linked."""
    with (
        _patch_git("sync_submodules"),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update", _fails_on_account_closing) as mock_update,
    ):
        result = project.invoke(submodule.update, ["--force"], catch_exceptions=True)
    assert result.exit_code == 1
    # the healthy one was attempted too, whichever order they ran in
    assert {str(call.args[0]) for call in mock_update.call_args_list} == set(SUBMODULES)
    failed_lines = [line for line in result.output.splitlines() if line.startswith("✖")]
    # the one submodule, and the step it was part of
    assert len(failed_lines) == 2
    assert failed_lines[0].startswith(f"✖ {SUBMODULES[0]}")
    assert failed_lines[1] == "✖ Updating submodules"
    assert "1 task(s) failed" in result.output
    assert "Please inspect the logs for details." in result.output


@with_submodules
def test_init_does_not_print_the_addons_path_when_a_submodule_failed(project):
    """An incomplete ENV ADDONS_PATH pasted into a Dockerfile is worse than none."""
    with _patch_git(
        "submodule_init", lambda info: _fails_on_account_closing(info.path)
    ):
        result = project.invoke(submodule.init, [], catch_exceptions=True)
    assert result.exit_code == 1
    assert "1 task(s) failed" in result.output
    assert "ENV ADDONS_PATH" not in result.output


@with_submodules
def test_update_writes_nothing_to_the_terminal_showing_the_display(project, capfd):
    """Whether a helper reports through ui.echo or runs a command, what it says
    lands in the submodule's log -- written raw it would corrupt the display.

    The two escape through different channels, so they are looked for in
    different places: ui.echo would reach the click runner's own buffer, while
    a command inheriting our file descriptors would reach the real ones.
    """

    def submodule_update(path, *args, **kwargs):
        ui.echo("chatty progress report")
        os_exec.run(["sh", "-c", "echo to stdout; echo to stderr >&2"])

    with (
        mock.patch.object(
            submodule, "console", Console(force_terminal=True, width=100)
        ),
        _patch_git("sync_submodules"),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update", submodule_update),
    ):
        result = project.invoke(submodule.update, ["--force"], catch_exceptions=True)
    assert result.exit_code == 0
    # a task that went fine leaves nothing of what it said on its row, either
    assert "chatty progress report" not in result.output
    captured = capfd.readouterr()
    assert "to stdout" not in captured.out + captured.err
    assert "to stderr" not in captured.out + captured.err


@with_submodules
def test_update_filters_on_the_given_path(project):
    with (
        _patch_git("sync_submodules"),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update") as mock_update,
    ):
        result = project.invoke(
            submodule.update, [SUBMODULES[1], "--force"], catch_exceptions=True
        )
    assert result.exit_code == 0
    assert [str(call.args[0]) for call in mock_update.call_args_list] == [SUBMODULES[1]]


@with_submodules
def test_the_shared_state_is_resolved_before_the_submodules_start(project):
    """git-autoshare prints in-process when it cannot find its config, and the
    project manifest is parsed with a shared parser -- so the first use of
    either has to happen while one thread still owns the terminal, not from a
    worker with a display drawn over it.
    """
    events = []
    with (
        mock.patch.object(
            submodule.git,
            "preload_submodule_state",
            side_effect=lambda: events.append("preload"),
        ),
        _patch_git("sync_submodules"),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update", lambda *a, **kw: events.append("task")),
    ):
        result = project.invoke(submodule.update, ["--force"], catch_exceptions=True)
    assert result.exit_code == 0
    assert events[0] == "preload"
    assert events.count("preload") == 1
    assert events.count("task") == 2


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
)
def test_nothing_is_resolved_when_there_are_no_submodules(project):
    """No .gitmodules, so no display to draw and no shared state to fill."""
    with mock.patch.object(submodule.git, "preload_submodule_state") as mock_preload:
        result = project.invoke(submodule.update, [], catch_exceptions=False)
    assert result.exit_code == 0
    mock_preload.assert_not_called()


# ── upgrade, several submodules at a time ────────────────────────────────────


@with_submodules
def test_upgrade_runs_the_submodules_in_parallel(project):
    """The barrier only clears if both are in flight together."""
    both_in_flight = threading.Barrier(2, timeout=10)

    with (
        patch_attr(submodule.pm_utils.Repo, "has_pending_merges", lambda self: False),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update"),
        _patch_git("submodule_upgrade", lambda *a, **kw: both_in_flight.wait()),
    ):
        result = project.invoke(
            submodule.upgrade, ["--jobs", "2"], catch_exceptions=True
        )
    assert result.exit_code == 0, result.output


@with_submodules
def test_upgrade_resolves_the_target_branch_before_the_submodules_start(project):
    """Resolving it may prompt, and it is the same branch for all of them."""
    events = []

    with (
        patch_attr(submodule.pm_utils.Repo, "has_pending_merges", lambda self: True),
        mock.patch.object(submodule.pending, "purge_repos"),
        patch_attr(
            submodule.pm_utils.Repo,
            "rebuild_consolidation_branch",
            lambda self, **kw: events.append("rebuild"),
        ) as mock_rebuild,
        mock.patch.object(
            submodule.gh,
            "get_target_branch",
            side_effect=lambda: events.append("resolve") or "branch-1234",
        ) as mock_target_branch,
    ):
        result = project.invoke(submodule.upgrade, [], catch_exceptions=True)
    assert result.exit_code == 0, result.output
    mock_target_branch.assert_called_once()
    # resolved once, before either of them, and both get that same branch
    assert events == ["resolve", "rebuild", "rebuild"]
    assert all(
        call.kwargs == {"push": True, "target_branch": "branch-1234"}
        for call in mock_rebuild.call_args_list
    )


@with_submodules
def test_upgrade_rolls_a_failure_back_and_still_reports_it(project):
    """A half-upgraded submodule is worse than one left alone -- but rolling it
    back is not succeeding, so it is still reported and the run fails."""
    rolled_back = []

    def submodule_update(path, *args, **kwargs):
        # the second call for a path is the roll-back
        rolled_back.append(str(path))

    with (
        patch_attr(submodule.pm_utils.Repo, "has_pending_merges", lambda self: False),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update", submodule_update),
        _patch_git("submodule_upgrade", _fails_on_account_closing),
    ):
        result = project.invoke(submodule.upgrade, [], catch_exceptions=True)
    assert result.exit_code == 1
    assert "1 task(s) failed" in result.output
    # updated once each, and then a second time for the one that failed
    assert rolled_back.count(SUBMODULES[0]) == 2
    assert rolled_back.count(SUBMODULES[1]) == 1


@with_submodules
def test_upgrade_rereads_gitmodules_after_purging(project):
    """Disposing of an emptied merges file points a submodule's url back at
    the upstream, so what was read before the purge is out of date.

    Upgrading off the stale url fetches the company fork, which only ever held
    the consolidation branch and has no version branch to move to -- `git
    fetch <fork> 19.0` then fails with "couldn't find remote ref".
    """
    fork = "git@github.com:camptocamp/account-closing.git"
    upstream = "git@github.com:OCA/account-closing.git"
    Path(".gitmodules").write_text(
        f'[submodule "{SUBMODULES[0]}"]\n'
        f"\tpath = {SUBMODULES[0]}\n\turl = {fork}\n\tbranch = 16.0\n"
    )

    def purge(repos, jobs=None):
        # what `_handle_empty_merges_file` does on the way out
        Path(".gitmodules").write_text(
            f'[submodule "{SUBMODULES[0]}"]\n'
            f"\tpath = {SUBMODULES[0]}\n\turl = {upstream}\n\tbranch = 16.0\n"
        )
        return []

    with (
        patch_attr(submodule.pm_utils.Repo, "has_pending_merges", lambda self: False),
        mock.patch.object(submodule.pending, "purge_repos", side_effect=purge),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update"),
        _patch_git("submodule_upgrade") as mock_upgrade,
    ):
        result = project.invoke(submodule.upgrade, [], catch_exceptions=True)
    assert result.exit_code == 0, result.output
    # the url it upgrades from is the one the purge left behind
    assert mock_upgrade.call_args.args[1] == upstream


@with_submodules
def test_upgrade_rebuilds_before_it_upgrades(project):
    """Rebuilding a consolidation branch pushes to the company remote; reading
    the report of that is far easier when a dozen submodules being pulled are
    not interleaved with it. So the two are steps, not one fan-out.

    Asserted as "no upgrade had begun while a rebuild was still running", not
    as the order things finished in -- one fan-out would satisfy that by luck.
    """
    rebuilt = threading.Event()
    seen_by_the_upgrade = []
    # The first submodule has pending merges and is rebuilt; the second has
    # none and is upgraded.
    with_pending = {SUBMODULES[0]}

    def rebuild(self, **kwargs):
        # Long enough that an upgrade sharing the fan-out would start meanwhile
        time.sleep(0.05)
        rebuilt.set()

    with (
        patch_attr(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            lambda self: str(self.path) in with_pending,
        ),
        mock.patch.object(submodule.pending, "purge_repos", return_value=[]),
        mock.patch.object(submodule.gh, "get_target_branch", return_value="master"),
        patch_attr(submodule.pm_utils.Repo, "rebuild_consolidation_branch", rebuild),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update"),
        _patch_git(
            "submodule_upgrade",
            lambda *a, **kw: seen_by_the_upgrade.append(rebuilt.is_set()),
        ),
    ):
        result = project.invoke(submodule.upgrade, [], catch_exceptions=True)
    assert result.exit_code == 0, result.output
    assert seen_by_the_upgrade == [True]


@with_submodules
def test_upgrade_stops_when_a_rebuild_fails(project):
    """A consolidation branch that could not be rebuilt leaves the project in a
    state nobody asked for; upgrading the rest on top of it only adds
    movement to undo."""
    upgraded = []

    def explode(self, **kwargs):
        raise RuntimeError("aggregation failed")

    with (
        patch_attr(
            submodule.pm_utils.Repo,
            "has_pending_merges",
            lambda self: str(self.path) == SUBMODULES[0],
        ),
        mock.patch.object(submodule.pending, "purge_repos", return_value=[]),
        mock.patch.object(submodule.gh, "get_target_branch", return_value="master"),
        patch_attr(submodule.pm_utils.Repo, "rebuild_consolidation_branch", explode),
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update"),
        _patch_git("submodule_upgrade", lambda path, *a, **kw: upgraded.append(path)),
    ):
        result = project.invoke(submodule.upgrade, [], catch_exceptions=True)
    assert result.exit_code == 1, result.output
    assert upgraded == []


@with_submodules
@pytest.mark.parametrize(
    ("options", "asks"),
    [([], True), (["--force-branch", "17.0"], False)],
)
def test_upgrade_asks_about_an_unexpected_branch_unless_forced(project, options, asks):
    """A submodule tracking something other than the project's Odoo version is
    usually a mistake, so it is queried -- but naming the branch outright is
    already the answer to that question."""
    Path(".gitmodules").write_text(
        f'[submodule "{SUBMODULES[0]}"]\n'
        f"\tpath = {SUBMODULES[0]}\n"
        "\turl = git@github.com:OCA/account-closing.git\n"
        "\tbranch = 15.0\n"
    )
    with (
        patch_attr(submodule.pm_utils.Repo, "has_pending_merges", lambda self: False),
        mock.patch.object(submodule.pending, "purge_repos", return_value=[]),
        mock.patch.object(
            submodule.ui, "ask_confirmation", return_value=True
        ) as mock_ask,
        _patch_git("sync_submodules"),
        _patch_git("register_submodules"),
        _patch_git("submodule_update"),
        _patch_git("submodule_upgrade") as mock_upgrade,
    ):
        result = project.invoke(submodule.upgrade, options, catch_exceptions=True)
    assert result.exit_code == 0, result.output
    assert mock_ask.called is asks
    # either way it is upgraded; the question is only whether one was asked
    assert mock_upgrade.called
