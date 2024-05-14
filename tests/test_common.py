# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import os
import subprocess
from unittest.mock import patch

from .common import fake_project_root, mock_subprocess_run


def test_mock_subprocess_run():
    mock_fn = mock_subprocess_run([{"args": ["ls", "-l"], "stdout": "file1\nfile2\n"}])
    with patch("subprocess.run", mock_fn):
        res = subprocess.run(["ls", "-l"], check=False)
        assert res.stdout.splitlines() == ["file1", "file2"]


def test_mock_subprocess_run_fail():
    mock_fn = mock_subprocess_run([{"args": ["ls", "-l"], "stdout": "file1\nfile2\n"}])
    with patch("subprocess.run", mock_fn):
        try:
            subprocess.run(["ls", "-a"], check=False)
        except AssertionError as exc:
            assert exc.args == ("Wrong args ['ls', '-a'], expecting ['ls', '-l']",)


def test_mock_subprocess_run_side_effect():
    with fake_project_root():

        def sim_touch(fname):
            open(fname, "w").close()

        mock_fn = mock_subprocess_run(
            [
                {
                    "args": ["touch", "foo"],
                    "sim_call": sim_touch,
                    "sim_call_args": ["foo"],
                }
            ]
        )
        with patch("subprocess.run", mock_fn):
            res = subprocess.run(["touch", "foo"], check=False)
            assert res.returncode == 0
            assert os.path.isfile("foo")
        os.unlink("foo")
