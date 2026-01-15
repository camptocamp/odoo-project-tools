# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import datetime
from unittest import mock

from odoo_tools.cli import release
from odoo_tools.cli.project import init
from odoo_tools.utils.config import config

from .common import (
    compare_line_by_line,
    fake_project_root,
    mock_pending_merge_repo_paths,
)


def test_make_bumpversion_cmd():
    cmd = release.make_bumpversion_cmd("patch")
    assert cmd == "bumpversion --list patch"
    cmd = release.make_bumpversion_cmd("patch", new_version="14.0.1.2.0")
    assert cmd == "bumpversion --list --new-version 14.0.1.2.0 patch"
    cmd = release.make_bumpversion_cmd("patch", new_version="14.0.1.2.0", dry_run=True)
    assert cmd == "bumpversion --list --new-version 14.0.1.2.0 --dry-run patch"


def test_make_towncrier_cmd():
    cmd = release.make_towncrier_cmd("16.0.1.0.0")
    assert cmd == "towncrier build --yes --version=16.0.1.0.0"


def test_bump():
    with fake_project_root(
        proj_version="14.0.0.1.0", mock_marabunta_file=True
    ) as runner:
        ver_file = config.version_file_rel_path
        with ver_file.open() as fd:
            assert fd.read() == "14.0.0.1.0"
        # run init to get all files ready (eg: bumpversion)
        runner.invoke(init, catch_exceptions=False)
        result = runner.invoke(
            release.bump, ["--type", "patch"], catch_exceptions=False
        )
        with ver_file.open() as fd:
            assert fd.read() == "14.0.0.1.1"
        result = runner.invoke(
            release.bump, ["--type", "minor"], catch_exceptions=False
        )
        with ver_file.open() as fd:
            assert fd.read() == "14.0.0.2.0"
        result = runner.invoke(
            release.bump, ["--type", "major"], catch_exceptions=False
        )
        with ver_file.open() as fd:
            assert fd.read() == "14.0.1.0.0"
        result = runner.invoke(
            release.bump,
            ["--type", "major", "--new-version", "15.0.0.0.1"],
            catch_exceptions=False,
        )
        with ver_file.open() as fd:
            assert fd.read() == "15.0.0.0.1"
        result = runner.invoke(
            release.bump, ["--type", "major", "--dry-run"], catch_exceptions=False
        )
        assert result.output.splitlines() == [
            "Running: bumpversion --list --dry-run major",
            "New version: 15.0.1.0.0",
        ]
        with ver_file.open() as fd:
            assert fd.read() == "15.0.0.0.1"
        assert result.exit_code == 0


def test_bump_changelog():
    with fake_project_root(
        proj_version="14.0.0.1.0", mock_marabunta_file=True
    ) as runner:
        # run init to get all files ready (eg: bumpversion)
        runner.invoke(init, catch_exceptions=False)
        hist_part_1 = (
            ".. :changelog:\n"
            ".. DO NOT EDIT. File is generated from fragments.\n\n"
            "Release History\n"
            "---------------\n\n"
            ".. towncrier release notes start\n\n"
        )
        hist_part_2 = (
            "14.0.0.1.0 (2011-10-09)\n" "+++++++++++++++++++++++\n\n" "* Blah\n"
        )
        changes = (
            ("Fixed a thing!", "./changes.d/1234.bug"),
            ("Added a thing!", "./changes.d/2345.feat"),
        )
        for change, path in changes:
            with open(path, "w") as fd:
                fd.write(change)
        with open("HISTORY.rst", "w") as fd:
            fd.write(hist_part_1 + hist_part_2)
        result = runner.invoke(
            release.bump, ["--type", "minor"], catch_exceptions=False, input="n"
        )
        new_part = (
            f"14.0.0.2.0 ({datetime.date.today():%Y-%m-%d})\n"
            "+++++++++++++++++++++++\n\n"
            "**Features and Improvements**\n"
            "* 2345: Added a thing!\n\n"
            "**Bugfixes**\n"
            # Note the 2 empty lines to separate versions
            "* 1234: Fixed a thing!\n\n\n"
        )

        expected = hist_part_1 + new_part + hist_part_2
        with open("HISTORY.rst") as fd:
            compare_line_by_line(fd.read(), expected)
        assert result.output.splitlines() == [
            "Running: bumpversion --list minor",
            "Running: towncrier build --yes --version=14.0.0.2.0",
            "Updating marabunta migration file",
            "Push local branches? [y/N]: n",
        ]
        assert result.exit_code == 0


def test_bump_update_marabunta_file():
    with fake_project_root(
        proj_version="14.0.0.1.0", mock_marabunta_file=True
    ) as runner:
        # run init to get all files ready (eg: bumpversion)
        runner.invoke(init, catch_exceptions=False)
        result = runner.invoke(
            release.bump, ["--type", "minor"], catch_exceptions=False, input="\n"
        )
        content = config.marabunta_mig_file_rel_path.read_text()
        # TODO: improve these checks
        assert "14.0.0.2.0" in content
        assert result.output.splitlines() == [
            "Running: bumpversion --list minor",
            "Running: towncrier build --yes --version=14.0.0.2.0",
            "Updating marabunta migration file",
            "Push local branches? [y/N]: ",
        ]
        assert result.exit_code == 0


def test_bump_update_without_marabunta_file():
    with fake_project_root(
        proj_version="14.0.0.1.0",
        proj_cfg=dict(marabunta_mig_file_rel_path=None),
        mock_marabunta_file=False,
    ) as runner:
        # run init to get all files ready (eg: bumpversion)
        runner.invoke(init, catch_exceptions=False)
        result = runner.invoke(
            release.bump, ["--type", "minor"], catch_exceptions=False, input="\n"
        )
        assert result.output.splitlines() == [
            "Running: bumpversion --list minor",
            "Running: towncrier build --yes --version=14.0.0.2.0",
            "Push local branches? [y/N]: ",
        ]
        assert result.exit_code == 0


def test_bump_push_no_repo():
    with fake_project_root(
        proj_version="14.0.0.1.0", mock_marabunta_file=True
    ) as runner:
        # run init to get all files ready (eg: bumpversion)
        runner.invoke(init, catch_exceptions=False)
        result = runner.invoke(
            release.bump, ["--type", "minor"], catch_exceptions=False, input="y"
        )
        assert result.output.splitlines() == [
            "Running: bumpversion --list minor",
            "Running: towncrier build --yes --version=14.0.0.2.0",
            "Updating marabunta migration file",
            "Push local branches? [y/N]: y",
            "No repo to push",
        ]
        assert result.exit_code == 0


# TODO: test more cases
def test_bump_push_repo_with_pending_merge():
    ran_cmd = []

    def mocked_run(cmd):
        ran_cmd.append(cmd)

    with (
        fake_project_root(
            proj_version="14.0.0.1.0", mock_marabunta_file=True
        ) as runner,
        mock.patch("odoo_tools.utils.pending_merge.run", mocked_run),
    ):
        mock_pending_merge_repo_paths("edi-framework")
        # run init to get all files ready (eg: bumpversion)
        runner.invoke(init, catch_exceptions=False)
        result = runner.invoke(
            release.bump, ["--type", "minor"], catch_exceptions=False, input="y"
        )
        assert result.output.splitlines() == [
            "Running: bumpversion --list minor",
            "Running: towncrier build --yes --version=14.0.0.2.0",
            "Updating marabunta migration file",
            "Push local branches? [y/N]: y",
            "Pushing odoo/external-src/edi-framework",
            "Impacted repos:",
            "odoo/external-src/edi-framework",
        ]
        assert ran_cmd == [
            "git config remote.camptocamp.url",
            "git push -f -v camptocamp HEAD:refs/heads/merge-branch-1234-14.0.0.2.0",
        ]
        assert result.exit_code == 0
