# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

import pytest

from odoo_tools.cli.cloud import cli as cloud_cli

from .common import mock_subprocess_run


def test_dump_download(project):
    """Test dump download command with defaults."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "download",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                ],
            }
        ]
    )
    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
    ):
        result = project.invoke(cloud_cli, ["dump", "download"], catch_exceptions=False)
        assert result.exit_code == 0
        mock_fn.assert_completed_calls()


def test_dump_download_with_different_customer_platform(project):
    """Test dump download command with explicit parameters."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "fr",
                    "download",
                    "--customer",
                    "test-customer",
                    "--env",
                    "labs.test",
                ],
            }
        ]
    )
    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
    ):
        result = project.invoke(
            cloud_cli,
            [
                "dump",
                "download",
                "--platform",
                "fr",
                "--customer",
                "test-customer",
                "--env",
                "labs.test",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        mock_fn.assert_completed_calls()


def test_dump_download_specific_dump(project):
    """Test dump download command with specific dump name."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "download",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                    "--name",
                    "specific_dump.sql.gpg",
                ],
            }
        ]
    )
    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
    ):
        result = project.invoke(
            cloud_cli,
            [
                "dump",
                "download",
                "--name",
                "specific_dump.sql.gpg",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        mock_fn.assert_completed_calls()


def test_dump_download_with_restore(project):
    """Test dump download command with restore option."""
    import json
    from pathlib import Path

    mock_dumps = [{"name": "latest_dump.sql.gpg"}]
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "list",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                    "--raw",
                ],
                "stdout": json.dumps(mock_dumps).encode(),
            },
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "download",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                    "--name",
                    "latest_dump.sql.gpg",
                ],
            },
        ]
    )

    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
        mock.patch(
            "odoo_tools.cli.cloud.utils.db.create_db_from_db_dump"
        ) as mock_create_db,
    ):
        result = project.invoke(
            cloud_cli,
            [
                "dump",
                "download",
                "--restore-to-db",
                "test_db",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        mock_fn.assert_completed_calls()
        mock_create_db.assert_called_once_with("test_db", Path("latest_dump.sql"))


def test_dump_create(project):
    """Test dump create command."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "dump",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                ],
            }
        ]
    )
    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
    ):
        result = project.invoke(
            cloud_cli,
            ["dump", "create"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        mock_fn.assert_completed_calls()


def test_dump_upload_from_file(project):
    """Test dump upload command with file path."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "dump",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                    "-i",
                    "test_dump.sql",
                ],
            }
        ]
    )

    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
    ):
        # Create a temporary file
        with open("test_dump.sql", "w") as f:
            f.write("test content")

        result = project.invoke(
            cloud_cli,
            [
                "dump",
                "upload",
                "test_dump.sql",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        mock_fn.assert_completed_calls()


def test_dump_upload_from_db(project):
    """Test dump upload command with database."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "dump",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                    "-i",
                    "db_dump.sql",
                ],
            }
        ]
    )

    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
        mock.patch(
            "odoo_tools.cli.cloud.utils.db.dump_db", return_value="db_dump.sql"
        ) as mock_dump_db,
    ):
        result = project.invoke(
            cloud_cli,
            [
                "dump",
                "upload",
                "--from-db",
                "test_db",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        mock_fn.assert_completed_calls()
        mock_dump_db.assert_called_once_with("test_db")


def test_dump_upload_missing_params(project):
    """Test dump upload command with missing parameters."""
    result = project.invoke(
        cloud_cli,
        ["dump", "upload"],
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert (
        "You must provide either DUMP_PATH or --from-db, but not both" in result.output
    )


@pytest.mark.project_setup(extra_files={"test_dump.sql": "empty"})
def test_dump_upload_both_params(project):
    """Test dump upload command with both parameters (should fail)."""
    result = project.invoke(
        cloud_cli,
        [
            "dump",
            "upload",
            "test_dump.sql",
            "--from-db",
            "test_db",
        ],
        catch_exceptions=True,
    )
    assert result.exit_code != 0, result.output
    assert (
        "You must provide either DUMP_PATH or --from-db, but not both" in result.output
    )


def test_dump_restore_from_prod(project):
    """Test dump restore from prod command."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "restore",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                    "--from-prod",
                ],
            }
        ]
    )

    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
    ):
        result = project.invoke(
            cloud_cli,
            ["dump", "restore", "--from-prod"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        mock_fn.assert_completed_calls()


def test_dump_restore(project):
    """Test dump restore command."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "restore",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                    "--name",
                    "test_dump.sql.gpg",
                ],
            }
        ]
    )

    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
    ):
        result = project.invoke(
            cloud_cli,
            [
                "dump",
                "restore",
                "test_dump.sql.gpg",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        mock_fn.assert_completed_calls()


def test_dump_restore_missing_params(project):
    """Test dump restore command with missing parameters."""
    result = project.invoke(
        cloud_cli,
        ["dump", "restore"],
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert (
        "You must provide either DUMP_NAME or --from-prod, but not both"
        in result.output
    )


def test_dump_restore_both_params(project):
    """Test dump restore command with both parameters (should fail)."""
    result = project.invoke(
        cloud_cli,
        [
            "dump",
            "restore",
            "test_dump.sql.gpg",
            "--from-prod",
        ],
        catch_exceptions=True,
    )
    assert result.exit_code != 0, result.output
    assert (
        "You must provide either DUMP_NAME or --from-prod, but not both"
        in result.output
    )


def test_dump_list(project):
    """Test dump list command."""
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "celebrimbor_cli",
                    "--platform",
                    "ch",
                    "list",
                    "--customer",
                    "acme",
                    "--env",
                    "int",
                ],
            }
        ]
    )

    with (
        mock.patch("odoo_tools.cli.cloud.utils.os_exec.has_exec", return_value=True),
        mock.patch("subprocess.run", mock_fn),
    ):
        result = project.invoke(
            cloud_cli,
            ["dump", "list"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        mock_fn.assert_completed_calls()
