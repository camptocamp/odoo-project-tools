# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from unittest.mock import patch

import pytest

from odoo_tools.utils import misc as misc_utils

from .common import mock_subprocess_run


def test_parse_ini_key():
    ini = "[avgheader]\nfoo = 1\nbaz = two"
    assert misc_utils.get_ini_cfg_key(ini, "avgheader", "foo") == "1"
    assert misc_utils.get_ini_cfg_key(ini, "avgheader", "baz") == "two"


def test_parse_ini_no_header_key():
    ini = "foo = 1\nbaz = two"
    assert misc_utils.get_ini_cfg_key(ini, "avgheader", "foo") == "1"
    assert misc_utils.get_ini_cfg_key(ini, "avgheader", "baz") == "two"


@pytest.mark.project_setup(
    manifest=dict(odoo_version="15.0"),
    proj_version="15.0.1.1.0",
    extra_files={"Dockerfile": "FROM ghcr.io/camptocamp/odoo-enterprise:15.0-latest\n"},
)
@pytest.mark.usefixtures("all_template_versions")
def test_get_docker_image_commit_hashes():
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "docker",
                    "run",
                    "--quiet",
                    "--rm",
                    "--pull",
                    "always",
                    "--entrypoint",
                    "printenv",
                    "ghcr.io/camptocamp/odoo-enterprise:15.0-latest",
                ],
                "stdout": "Starting with UID : 1043\nRunning without demo data\nPATH=/bin,/usr/bin\nCORE_HASH=12345\nENTERPRISE_HASH=56789\n",
            }
        ]
    )
    with patch("subprocess.run", mock_fn):
        res = misc_utils.get_docker_image_commit_hashes()
        assert res == ("12345", "56789")
