# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import responses

from odoo_tools.utils import pypi as pypi_utils

from .common import fake_project_root

# NOTE: run this test only locally as it makes a real call to pypi
# def test_get_last_pypi_version_real():
#     pkg_name = "odoo-addon-edi_oca"
#     latest_version = pypi_utils.get_last_pypi_version(pkg_name)
#     assert latest_version == "15.0.1.5.0.1"


def test_get_last_pypi_version():
    pkg_name = "odoo-addon-edi-oca"
    data = {
        "info": {"version": "15.0.1.6.0"},
        "releases": {
            "15.0.1.0.0": [],
            "15.0.1.2.0": [],
            "15.0.1.6.0": [],
            "16.0.1.0.0": [],
        },
    }
    with responses.RequestsMock() as rsps:
        with fake_project_root(
            manifest=dict(odoo_version="15.0"), proj_version="15.0.0.1.0"
        ):
            rsps.add(
                responses.GET,
                f"https://pypi.org/pypi/{pkg_name}/json",
                json=data,
                status=200,
                content_type="application/json",
            )
            latest_version = pypi_utils.get_last_pypi_version(pkg_name)
            assert latest_version == "15.0.1.6.0"


def test_odoo_name_to_pkg_name():
    assert pypi_utils.odoo_name_to_pkg_name("edi_oca") == "odoo-addon-edi_oca"
    assert (
        pypi_utils.odoo_name_to_pkg_name("odoo-addon-edi_oca") == "odoo-addon-edi_oca"
    )
    assert pypi_utils.odoo_name_to_pkg_name("foo") == "odoo-addon-foo"
    assert (
        pypi_utils.odoo_name_to_pkg_name("foo", odoo_version="14.9")
        == "odoo14-addon-foo"
    )


def test_odoo_name_to_pkg_name_with_odoo_version():
    assert (
        pypi_utils.odoo_name_to_pkg_name("edi_oca", odoo_version="13.0")
        == "odoo13-addon-edi_oca"
    )
    assert (
        pypi_utils.odoo_name_to_pkg_name("edi_oca", odoo_version="14.0")
        == "odoo14-addon-edi_oca"
    )
    assert (
        pypi_utils.odoo_name_to_pkg_name("edi_oca", odoo_version="15.0")
        == "odoo-addon-edi_oca"
    )
    assert (
        pypi_utils.odoo_name_to_pkg_name("edi_oca", odoo_version="16.0")
        == "odoo-addon-edi_oca"
    )


def test_odoo_name_to_pkg_name_with_odoo_serie():
    assert (
        pypi_utils.odoo_name_to_pkg_name("edi_oca", odoo_serie="13")
        == "odoo13-addon-edi_oca"
    )
    assert (
        pypi_utils.odoo_name_to_pkg_name("edi_oca", odoo_serie="14")
        == "odoo14-addon-edi_oca"
    )
    assert (
        pypi_utils.odoo_name_to_pkg_name("edi_oca", odoo_serie="15")
        == "odoo-addon-edi_oca"
    )
    assert (
        pypi_utils.odoo_name_to_pkg_name("edi_oca", odoo_serie="16")
        == "odoo-addon-edi_oca"
    )
