# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from . import pypi, req


class Package:
    def __init__(self, name, odoo=True, req_filepath=None):
        self.name = name
        self.odoo = odoo
        self.pypi_name = name
        if self.odoo:
            self.pypi_name = pypi.odoo_name_to_pkg_name(name)
        self.req = req.get_addon_requirement(self.pypi_name, req_filepath=req_filepath)
        self.pinned_version = self.req.specs if self.req else None
        self.latest_version = pypi.get_last_pypi_version(self.pypi_name)

    def allowed_version(self, version):
        if not self.pinned_version:
            return True
        return req.allowed_version(version)

    def add_requirement(self, version=None, pr=None):
        req.add_requirement(
            self.pypi_name, version=version or self.latest_version, pr=pr
        )

    def replace_requirement(self, version=None, pr=None):
        req.replace_requirement(
            self.pypi_name, version=version or self.latest_version, pr=pr
        )

    def has_pending_merge(self):
        return "refs/pull" in self.req.line
