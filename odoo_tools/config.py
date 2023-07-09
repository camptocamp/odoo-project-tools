# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

# TODO: use a config file or an env file

from pathlib import PosixPath

confs = {
    "c2c_git_remote": "camptocamp",
    # Path where odoo source code is available
    # FIXME: new project structure won't have it
    "odoo_src_rel_path": "odoo/src",
    # Path where external sources are checked out
    # being submodules or not.
    # FIXME: will be dev-src
    "ext_src_rel_path": "odoo/external-src",
    # FIXME: will be addons?
    "local_src_rel_path": "odoo/local-src",
    "pending_merge_rel_path": "pending-merges.d",
    # FIXME: will be VERSION?
    "version_file_rel_path": "odoo/VERSION",
    "marabunta_mig_file_rel_path": "odoo/migration.yml",
}


def get_conf_key(key):
    v = confs.get(key)
    if key.endswith("_path"):
        v = PosixPath(v)
    return v
