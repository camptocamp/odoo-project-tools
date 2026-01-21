# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from . import pypi, req
from .proj import get_odoo_serie


class Package:
    def __init__(self, name, odoo=True, req_filepath=None):
        self.name = name
        self.odoo = odoo
        self.pypi_name = name
        self.req_filepath = req_filepath
        if self.odoo:
            self.pypi_name = pypi.odoo_name_to_pkg_name(
                name, odoo_serie=get_odoo_serie()
            )
        self.latest_version = pypi.get_last_pypi_version(self.pypi_name, odoo=odoo)
        self._req = None

    @property
    def req(self):
        if self._req is not None:
            return self._req
        self._req = req.get_addon_requirement(
            self.pypi_name, req_filepath=self.req_filepath
        )
        return self._req

    @property
    def pinned_version(self):
        return self.req.specs if self.req else None

    @property
    def uri(self):
        return self.req.uri if self.req else None

    def allowed_version(self, version):
        if not self.pinned_version:
            return True
        return req.allowed_version(self.req, version)

    def add_requirement(self, version=None, pr=None, editable=False, use_wool=None):
        req.add_requirement(
            self.pypi_name,
            version=version or self.latest_version,
            pr=pr,
            editable=editable,
            req_filepath=self.req_filepath,
            use_wool=use_wool,
        )
        self._req = None

    def replace_requirement(self, version=None, pr=None, editable=False, use_wool=None):
        req.replace_requirement(
            self.pypi_name,
            version=version or self.latest_version,
            pr=pr,
            editable=editable,
            req_filepath=self.req_filepath,
            use_wool=use_wool,
        )
        self._req = None

    def add_or_replace_requirement(
        self, version=None, pr=None, editable=False, use_wool=None
    ):
        if self.has_requirement():
            self.replace_requirement(
                version=version, pr=pr, editable=editable, use_wool=use_wool
            )
        else:
            self.add_requirement(
                version=version, pr=pr, editable=editable, use_wool=use_wool
            )

    def has_pending_merge(self):
        return (
            "refs/pull" in self.req.line if self.req else False
        ) or self.is_editable()

    def has_requirement(self):
        return bool(self.pinned_version)

    def is_editable(self):
        return self.req.editable if self.req else False

    def is_local(self):
        return self.req.local_file if self.req else False
