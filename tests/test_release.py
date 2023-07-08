# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import datetime

from odoo_tools import release
from odoo_tools.config import get_conf_key
from odoo_tools.project import init

from .common import compare_line_by_line, fake_project_root
from .fixtures import clear_caches  # noqa


def test_make_bumpversion_cmd():
    cmd = release.make_bumpversion_cmd("patch")
    assert cmd == "bumpversion patch"
    cmd = release.make_bumpversion_cmd("patch", new_version="14.0.1.2.0")
    assert cmd == "bumpversion --new-version 14.0.1.2.0 patch"
    cmd = release.make_bumpversion_cmd("patch", new_version="14.0.1.2.0", dry_run=True)
    assert cmd == "bumpversion --new-version 14.0.1.2.0 --dry-run --list patch"


def test_make_towncrier_cmd():
    cmd = release.make_towncrier_cmd("16.0.1.0.0")
    assert cmd == "towncrier build --yes --version=16.0.1.0.0"


def test_bump():
    ver_file = get_conf_key("version_file_rel_path")
    with fake_project_root(proj_version="14.0.0.1.0") as runner:
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
            "Running: bumpversion --dry-run --list major",
            "New version: 15.0.1.0.0",
        ]
        with ver_file.open() as fd:
            assert fd.read() == "15.0.0.0.1"
        assert result.exit_code == 0


def test_bump_changelog():
    with fake_project_root(proj_version="14.0.0.1.0") as runner:
        # run init to get all files ready (eg: bumpversion)
        runner.invoke(init, catch_exceptions=False)
        changes = (
            ("Fixed a thing!", "./changes.d/1234.bugfix"),
            ("Added a thing!", "./changes.d/2345.feature"),
        )
        for change, path in changes:
            with open(path, "w") as fd:
                fd.write(change)
        result = runner.invoke(
            release.bump, ["--type", "minor"], catch_exceptions=False
        )
        date = datetime.date.today().strftime("%Y-%m-%d")
        expected = "\n".join(
            (
                f"14.0.0.2.0 ({date})",
                "+++++++++++++++++++++++",
                "\n**Features and Improvements**\n"
                "* 2345: Added a thing!"
                "\n**Bugfixes**\n"
                "* 1234: Fixed a thing!",
            )
        )
        with open("HISTORY.rst") as fd:
            compare_line_by_line(fd.read(), expected)
        assert result.output.splitlines() == [
            "Running: bumpversion minor",
            "Running: towncrier build --yes --version=14.0.0.2.0",
        ]
        assert result.exit_code == 0
