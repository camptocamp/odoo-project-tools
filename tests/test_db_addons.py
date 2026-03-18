# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from unittest.mock import patch

import pytest

from odoo_tools.cli.db import cli

FAKE_ADDONS = [
    ("base", "Base", "16.0.1.0.0"),
    ("sale", "Sales", "16.0.1.0.0"),
    ("account", "Invoicing", "16.0.1.1.0"),
]


@pytest.mark.project_setup(manifest={"odoo_version": "16.0"})
class TestAddonsList:
    def test_table_output(self, project):
        with patch("odoo_tools.utils.db.execute_db_request", return_value=FAKE_ADDONS):
            result = project.invoke(cli, ["addons", "list"])
        assert result.exit_code == 0
        assert "base" in result.output
        assert "Sales" in result.output
        assert "16.0.1.1.0" in result.output

    def test_json_output(self, project):
        with patch("odoo_tools.utils.db.execute_db_request", return_value=FAKE_ADDONS):
            result = project.invoke(cli, ["addons", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0] == {"name": "base", "title": "Base", "version": "16.0.1.0.0"}
        assert all({"name", "title", "version"} == set(d.keys()) for d in data)

    def test_custom_database(self, project):
        with patch(
            "odoo_tools.utils.db.execute_db_request", return_value=FAKE_ADDONS
        ) as mock_exec:
            result = project.invoke(cli, ["addons", "list", "--database", "mydb"])
        assert result.exit_code == 0
        mock_exec.assert_called_once()
        assert mock_exec.call_args[0][0] == "mydb"

    def test_empty_result(self, project):
        with patch("odoo_tools.utils.db.execute_db_request", return_value=[]):
            result = project.invoke(cli, ["addons", "list"])
        assert result.exit_code == 0
        assert "No installed addons found" in result.output
