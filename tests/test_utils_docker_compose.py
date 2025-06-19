from unittest.mock import patch

from odoo_tools.utils import docker_compose

from .common import mock_subprocess_run


def test_version():
    mock_fn = mock_subprocess_run(
        [
            {
                "args": ["docker", "compose", "version", "--short"],
                "stdout": b"2.36.2",
            }
        ]
    )
    with patch("subprocess.run", mock_fn):
        version = docker_compose.get_version()
    assert version == [2, 36, 2]


def test_pull():
    cmd = docker_compose.pull("odoo", pull_policy="always")
    assert cmd == ["docker", "compose", "pull", "--policy", "always", "--quiet", "odoo"]


def test_down():
    cmd = docker_compose.down()
    assert cmd == ["docker", "compose", "down"]


def test_run_version_2_36():
    mock_fn = mock_subprocess_run(
        [
            {
                "args": ["docker", "compose", "version", "--short"],
                "stdout": b"2.36.2",
            }
        ]
    )
    with patch("subprocess.run", mock_fn):
        cmd = docker_compose.run(
            "odoo",
            ["odoo"],
            quiet=True,
            environment={"MIGRATE": "false", "DB_NAME": "testdb"},
            interactive=False,
            port_mapping=[(8080, 8069)],
        )
        print(cmd)
        assert cmd == [
            "docker",
            "compose",
            "run",
            "--rm",
            "--interactive=false",
            "-e",
            "MIGRATE=false",
            "-e",
            "DB_NAME=testdb",
            "--quiet",
            "--publish",
            "8080:8069",
            "odoo",
            "odoo",
        ]


def test_run_version_2_33():
    mock_fn = mock_subprocess_run(
        [
            {
                "args": ["docker", "compose", "version", "--short"],
                "stdout": b"2.33.1",
            }
        ]
    )
    with patch("subprocess.run", mock_fn):
        cmd = docker_compose.run(
            "odoo",
            ["odoo"],
            quiet=True,
            environment={"MIGRATE": "false", "DB_NAME": "testdb"},
            interactive=False,
            port_mapping=[(8080, 8069)],
        )
        print(cmd)
        assert cmd == [
            "docker",
            "compose",
            "run",
            "--rm",
            "--interactive=false",
            "-e",
            "MIGRATE=false",
            "-e",
            "DB_NAME=testdb",
            "--quiet-pull",
            "--publish",
            "8080:8069",
            "odoo",
            "odoo",
        ]
