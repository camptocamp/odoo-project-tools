# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import logging
import re

import requests
from packaging.version import Version

from .proj import get_odoo_serie

TMP_CACHE = {}

_logger = logging.getLogger(__name__)


def get_last_pypi_version(pkg_name, odoo=True):
    # NOTE: this resp might be very big.
    # If it gets slow or burns too much mem try to find another way.
    if odoo:
        odoo_serie = get_odoo_serie()
        pkg_name = odoo_name_to_pkg_name(pkg_name, odoo_serie=odoo_serie)
    if pkg_name in TMP_CACHE:
        return TMP_CACHE[pkg_name]
    url = f"https://pypi.org/pypi/{pkg_name}/json"
    response = requests.get(url)
    try:
        response.raise_for_status()
    except requests.HTTPError:
        _logger.debug("%s not found on pypy at %s", pkg_name, url)
        return None
    data = response.json()
    if odoo:
        versions = [
            Version(version)
            for version in data["releases"]
            if version.startswith(odoo_serie)
        ]
        if versions:
            latest_version = str(max(versions))
        else:
            latest_version = f"{odoo_serie or '0'}.0.0.0.0-pre"
    else:
        latest_version = data["info"]["version"]
    TMP_CACHE[pkg_name] = latest_version
    return latest_version


def odoo_name_to_pkg_name(odoo_name, odoo_version="", odoo_serie=""):
    if re.match(r"odoo(\d\d)?-addon", odoo_name):
        return odoo_name
    if not odoo_serie and odoo_version:
        odoo_serie = odoo_version.split(".")[0]
    odoo_serie = odoo_serie if odoo_serie and int(odoo_serie) < 15 else ""
    return f"odoo{odoo_serie}-addon-{odoo_name}"


def pkg_name_to_odoo_name(pkg_name, odoo_version=""):
    return "".join(pkg_name.split("-", 2)[2:]).replace("-", "_")
