# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

from odoo_tools.project import init

from .common import fake_project_root, get_fixture


def test_init():
    with fake_project_root() as runner:
        result = runner.invoke(init, catch_exceptions=False)
        assert os.path.exists("docker-compose.override.yml")
        with open(".bumpversion.cfg") as fd:
            content = fd.read()
            expected = get_fixture("expected.bumpversion.cfg")
            # Compare line by line to ease debug in case of error
            for content_line, expected_line in zip(
                content.splitlines(), expected.splitlines()
            ):
                assert content_line == expected_line
        assert result.exit_code == 0
