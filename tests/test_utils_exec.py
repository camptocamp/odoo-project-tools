# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path

from click.testing import CliRunner

from odoo_tools.utils import os_exec as exec_utils


def test_run():
    runner = CliRunner()
    with runner.isolated_filesystem():
        cwd = Path()
        assert not (cwd / "foo").exists()
        exec_utils.run("mkdir -p foo/bar")
        exec_utils.run("touch foo/bar/pippo.txt")
        assert (cwd / "foo/bar/pippo.txt").exists()


def test_has_exec():
    assert exec_utils.has_exec("ls")
    assert exec_utils.has_exec("pytest")
    assert not exec_utils.has_exec("this_does_not_exist")
