# Copyright 2026 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo_tools.cli.db import cli

FAKE_DB_LIST = ["prod", "prod_cleanup", "prod_core", "staging", "testdb"]


class TestDbDrop:
    def test_no_match(self, project):
        with patch("odoo_tools.utils.db.get_db_list", return_value=FAKE_DB_LIST):
            result = project.invoke(cli, ["drop", "nope"])
        assert result.exit_code == 0
        assert "No databases found matching prefix" in result.output

    def test_confirmed(self, project):
        with (
            patch("odoo_tools.utils.db.get_db_list", return_value=FAKE_DB_LIST),
            patch("odoo_tools.utils.docker_compose.drop_db") as mock_drop_db,
            patch("odoo_tools.utils.os_exec.run") as mock_run,
        ):
            result = project.invoke(cli, ["drop", "prod"], input="y\n")
        assert result.exit_code == 0
        assert mock_drop_db.call_count == 3
        mock_drop_db.assert_any_call("prod")
        mock_drop_db.assert_any_call("prod_cleanup")
        mock_drop_db.assert_any_call("prod_core")
        assert mock_run.call_count == 3

    def test_aborted(self, project):
        with (
            patch("odoo_tools.utils.db.get_db_list", return_value=FAKE_DB_LIST),
            patch("odoo_tools.utils.os_exec.run") as mock_run,
        ):
            result = project.invoke(cli, ["drop", "prod"], input="n\n")
        assert result.exit_code != 0
        mock_run.assert_not_called()

    def test_yes_flag_skips_prompt(self, project):
        with (
            patch("odoo_tools.utils.db.get_db_list", return_value=FAKE_DB_LIST),
            patch("odoo_tools.utils.docker_compose.drop_db"),
            patch("odoo_tools.utils.os_exec.run") as mock_run,
        ):
            result = project.invoke(cli, ["drop", "prod", "--yes"])
        assert result.exit_code == 0
        assert mock_run.call_count == 3
