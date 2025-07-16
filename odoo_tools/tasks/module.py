# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

from invoke import task

from ..utils import db, ui


def get_addons_path():
    """Reconstruct addons_path based on known odoo module locations"""
    # TODO: change depending on new structure
    # use root_path to get root project directory
    addons_path = ["odoo/src/addons", "odoo/local-src"]
    ext_path = "odoo/external-src/"
    addons_path.extend(
        [ext_path + i for i in os.listdir(ext_path) if os.path.isdir(ext_path + i)]
    )
    return addons_path


class Module:
    def __init__(self, name):
        self.name = name

    @property
    def dir(self):
        """Gives the location of a module

        Search in know locations

        :returns directory

        """
        addons_path = get_addons_path()
        for folder in addons_path:
            if self.name in os.listdir(folder):
                return folder
        # TODO: change depending on new structure
        # use root_path to get root project directory
        if self.name == "base":
            return "odoo/src/odoo/addons"
        raise Exception(f"module {self.name} not found")

    @property
    def path(self):
        directory = self.dir
        return os.path.join(directory, self.name)

    def get_dependencies(self):
        if self.name == "base":
            return []
        path = self.path
        try:
            manifest_path = os.path.join(path, "__manifest__.py")
            with open(manifest_path) as f:
                return eval(f.read()).get("depends", [])
        except OSError:
            manifest_path = os.path.join(path, "__openerp__.py")
            with open(manifest_path) as f:
                return eval(f.read()).get("depends", [])

    @classmethod
    def get_installed_addons(cls, dbname="odoodb"):
        query = "SELECT name FROM ir_module_module WHERE state = 'installed';"
        result = db.execute_db_request(dbname, query)
        return [mod_name for [mod_name] in result]


@task
def where_is(ctx, module_name):
    """Locate a module"""
    print(Module(module_name).path)


@task
def installed(ctx, db_name="odoodb"):
    """List installed addons."""
    db_list = db.get_db_list()
    if db_name not in db_list:
        ui.exit_msg(
            f"Database {db_name} does not exist.\nAvailable: {', '.join(db_list)}"
        )
    res = Module.get_installed_addons(dbname=db_name)
    print("\n".join(sorted(res)))
