# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from pathlib import Path
from unittest import mock

import pytest

from odoo_tools.cli.password import cli as password_cli

PRE_PY_CONTENT = """\
env.user.password_crypt = '__GENERATED_ADMIN_PASSWORD__'
"""


PRE_PY_CONTENT_NO_PLACEHOLDER = """\
env.user.password_crypt = 'already_set'
"""


@pytest.mark.project_setup(
    extra_files={"odoo/songs/install/pre.py": PRE_PY_CONTENT},
)
def test_generate_admin_password(project):
    result = project.invoke(
        password_cli, ["generate-admin-password"], catch_exceptions=False
    )
    assert result.exit_code == 0
    assert "Admin password:" in result.output
    assert "Encrypted admin password:" in result.output
    # Verify placeholder was replaced
    pre_file = Path("odoo/songs/install/pre.py").read_text()
    assert "__GENERATED_ADMIN_PASSWORD__" not in pre_file
    assert "$pbkdf2-sha512$" in pre_file


@pytest.mark.project_setup(
    extra_files={"odoo/songs/install/pre.py": PRE_PY_CONTENT},
)
def test_generate_admin_password_store_in_lastpass(project):
    mock_process = mock.Mock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"", b"")

    mock_popen = mock.Mock(return_value=mock_process)

    with (
        mock.patch("odoo_tools.utils.lpass.os_exec.has_exec", return_value=True),
        mock.patch("odoo_tools.utils.lpass.Popen", mock_popen),
        mock.patch("odoo_tools.utils.lpass.os_exec.run"),
        mock.patch("odoo_tools.utils.lpass.time.sleep"),
    ):
        result = project.invoke(
            password_cli,
            ["generate-admin-password", "--store-in-lastpass"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    assert "Admin password:" in result.output
    assert "Password stored in LastPass" in result.output
    # Verify lpass was called twice (prod + integration)
    assert mock_popen.call_count == 2
    # Verify the lpass command args
    call_args = mock_popen.call_args_list[0]
    command = call_args[0][0]
    assert command[0] == "lpass"
    assert command[1] == "add"
    assert "acme_odoo" in command[-1]


@pytest.mark.project_setup(
    extra_files={"odoo/songs/install/pre.py": PRE_PY_CONTENT_NO_PLACEHOLDER},
)
def test_generate_admin_password_placeholder_not_found(project):
    result = project.invoke(
        password_cli,
        ["generate-admin-password"],
    )
    assert result.exit_code != 0
    assert "__GENERATED_ADMIN_PASSWORD__" in result.output


@pytest.mark.project_setup(
    extra_files={"odoo/songs/install/pre.py": PRE_PY_CONTENT},
)
def test_generate_admin_password_store_in_lastpass_no_lpass(project):
    with mock.patch("odoo_tools.utils.lpass.os_exec.has_exec", return_value=False):
        result = project.invoke(
            password_cli,
            ["generate-admin-password", "--store-in-lastpass"],
        )
    assert result.exit_code != 0
    assert "LastPass CLI is not available" in result.output
