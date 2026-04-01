# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import subprocess
from pathlib import Path
from unittest.mock import patch

from .common import MockSubprocessRun


def test_MockSubprocessRun():
    mock_fn = MockSubprocessRun([{"args": ["ls", "-l"], "stdout": "file1\nfile2\n"}])
    with patch("subprocess.run", mock_fn):
        res = subprocess.run(["ls", "-l"], check=False)
        assert res.stdout.splitlines() == ["file1", "file2"]


def test_MockSubprocessRun_fail():
    mock_fn = MockSubprocessRun([{"args": ["ls", "-l"], "stdout": "file1\nfile2\n"}])
    with patch("subprocess.run", mock_fn):
        try:
            subprocess.run(["ls", "-a"], check=False)
        except AssertionError as exc:
            assert exc.args == ("Wrong args ['ls', '-a'], expecting ['ls', '-l']",)


def test_MockSubprocessRun_side_effect(project):

    def sim_touch(fname):
        Path(fname).touch()

    temp_file = Path("foo")
    mock_fn = MockSubprocessRun(
        [
            {
                "args": ["touch", temp_file.name],
                "sim_call": sim_touch,
                "sim_call_args": [temp_file.name],
            }
        ]
    )
    with patch("subprocess.run", mock_fn):
        res = subprocess.run(["touch", str(temp_file)], check=False)
        assert res.returncode == 0
        assert temp_file.is_file()
    temp_file.unlink()
