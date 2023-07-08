# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

from odoo_tools.project import init

from .common import compare_line_by_line, fake_project_root, get_fixture
from .fixtures import clear_caches  # noqa


def test_init():
    with fake_project_root() as runner:
        result = runner.invoke(init, catch_exceptions=False)
        paths = (
            "docker-compose.override.yml",
            "changes.d/.gitkeep",
            "towncrier.toml",
            ".towncrier-template.rst",
        )
        for path in paths:
            assert os.path.exists(path), f"`{path}` missing"
        with open(".bumpversion.cfg") as fd:
            content = fd.read()
            expected = get_fixture("expected.bumpversion.cfg")
            compare_line_by_line(content, expected)
        assert result.exit_code == 0


def test_init_custom_version():
    with fake_project_root() as runner:
        result = runner.invoke(
            init,
            [
                "--version",
                "16.0.1.1.0",
            ],
            catch_exceptions=False,
        )
        assert os.path.exists("docker-compose.override.yml")
        with open(".bumpversion.cfg") as fd:
            content = fd.read()
            expected = get_fixture("expected.bumpversion.v2.cfg")
            compare_line_by_line(content, expected)
        assert result.exit_code == 0
