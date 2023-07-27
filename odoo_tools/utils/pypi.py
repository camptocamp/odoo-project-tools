# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import requests

TMP_CACHE = {}


def get_last_pypi_version(pkg_name, odoo=True):
    # NOTE: this resp might be very big.
    # If it gets slow or burns too much mem try to find another way.
    if odoo:
        pkg_name = odoo_name_to_pkg_name(pkg_name)
    if pkg_name in TMP_CACHE:
        return TMP_CACHE[pkg_name]
    response = requests.get(f"https://pypi.org/pypi/{pkg_name}/json")
    data = response.json()
    latest_version = data["info"]["version"]
    TMP_CACHE[pkg_name] = latest_version
    return latest_version


def odoo_name_to_pkg_name(odoo_name, odoo_version="", odoo_serie=""):
    if odoo_name.startswith("odoo-addon"):
        return odoo_name
    if not odoo_serie and odoo_version:
        odoo_serie = odoo_version.split(".")[0]
    odoo_serie = odoo_serie if odoo_serie and int(odoo_serie) < 15 else ""
    return f"odoo{odoo_serie}-addon-{odoo_name}"


def pkg_name_to_odoo_name(pkg_name, odoo_version=""):
    return "".join(pkg_name.split("-", 2)[2:]).replace("-", "_")
