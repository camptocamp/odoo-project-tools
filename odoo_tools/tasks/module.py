# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from ast import literal_eval
from pathlib import Path

from invoke import task


def get_addons_path():
    """Reconstruct addons_path based on known odoo module locations"""
    # TODO: change depending on new structure
    # use root_path to get root project directory
    odoo_dir = Path("odoo")
    addons_path = [
        odoo_dir / "src" / "addons",
        odoo_dir / "local-src",
    ]
    ext_path = odoo_dir / "external-src"
    addons_path.extend(dir_pth for dir_pth in ext_path.iter() if dir_pth.is_dir())
    return addons_path


class Module:
    def __init__(self, name):
        self.name = name

    @property
    def dir(self):
        """Gives the location of a module

        Search in known locations

        :returns directory

        """
        addons_path = get_addons_path()
        for folder in addons_path:
            if (folder / self.name).exists():
                return folder
        # TODO: change depending on new structure
        # use root_path to get root project directory
        if self.name == "base":
            return Path("odoo/src/odoo/addons")
        raise Exception(f"module {self.name} not found")

    @property
    def path(self):
        return self.dir / self.name

    def get_dependencies(self):
        if self.name == "base":
            return []
        manifest_path = self.path / "__manifest__.py"
        # Compatible with old Odoo versions
        openerp_path = self.path / "__openerp__.py"
        if not manifest_path.exists() and openerp_path.exists():
            manifest_path = openerp_path
        return literal_eval(manifest_path.read_text()).get("depends", [])


@task
def where_is(ctx, module_name):
    """Locate a module"""
    print(Module(module_name).path)
