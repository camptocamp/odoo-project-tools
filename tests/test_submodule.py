from unittest import mock

import pytest

from odoo_tools.cli import submodule
from odoo_tools.utils.path import build_path

from .common import mock_subprocess_run


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"), proj_version="16.0.1.2.3"
)
def test_init(project):
    gitmodules = build_path(".gitmodules")
    odoo_version = "16.0"
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "git",
                    "config",
                    "-f",
                    str(gitmodules),
                    "--get-regexp",
                    r"^submodule\..*\.path$",
                ],
                "stdout": """submodule.odoo/external-src/account-closing.path odoo/external-src/account-closing
submodule.odoo/external-src/account-financial-reporting.path odoo/external-src/account-financial-reporting
""",
            },
            {
                "args": [
                    "git",
                    "config",
                    "-f",
                    str(gitmodules),
                    "--get",
                    "submodule.odoo/external-src/account-closing.url",
                ],
                "stdout": "git@github.com:OCA/account-closing.git\n",
            },
            {
                "args": [
                    "git",
                    "autoshare-submodule-add",
                    "-b",
                    odoo_version,
                    "git@github.com:OCA/account-closing.git",
                    "odoo/external-src/account-closing",
                ],
            },
            {
                "args": [
                    "git",
                    "config",
                    "-f",
                    str(gitmodules),
                    "--get",
                    "submodule.odoo/external-src/account-financial-reporting.url",
                ],
                "stdout": "git@github.com:OCA/account-financial-reporting.git\n",
            },
            {
                "args": [
                    "git",
                    "autoshare-submodule-add",
                    "-b",
                    odoo_version,
                    "git@github.com:OCA/account-financial-reporting.git",
                    "odoo/external-src/account-financial-reporting",
                ],
            },
        ]
    )
    with mock.patch("subprocess.run", mock_fn):
        result = project.invoke(
            submodule.init,
            [],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
