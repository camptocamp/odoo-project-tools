# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

from click.testing import CliRunner

from odoo_tools.project import init


def test_init():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(init)
        assert os.path.exists("docker-compose.override.yml")
        assert os.path.exists(".bumpversion.cfg")
        assert result.exit_code == 0
