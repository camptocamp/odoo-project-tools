# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import responses

from odoo_tools.utils import pypi as pypi_utils

# NOTE: run this test only locally as it makes a real call to pypi
# def test_get_last_pypi_version_real():
#     pkg_name = "odoo-addon-edi_oca"
#     latest_version = pypi_utils.get_last_pypi_version(pkg_name)
#     assert latest_version == "15.0.1.5.0.1"


def test_get_last_pypi_version():
    pkg_name = "odoo-addon-edi-oca"
    data = {"info": {"version": "15.0.1.6.0"}}
    with responses.RequestsMock() as rsps:
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
        == "odoo-addon14-foo"
    )
