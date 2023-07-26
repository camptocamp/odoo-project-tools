# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from . import yaml


class MarabuntaFileHandler:
    def __init__(self, path_obj):
        self.path_obj = path_obj

    def load(self):
        return yaml.yaml_load(self.path_obj.open())

    def update(self, version, run_click_hook="post"):
        data = self.load()
        versions = data["migration"]["versions"]
        version_item = [x for x in versions if x["version"] == version]
        if version_item:
            version_item = version_item[0]
        else:
            version_item = {"version": version}
            versions.append(version_item)
        if not version_item.get("operations"):
            version_item["operations"] = {}
        operations = version_item["operations"]
        cmd = self._make_click_odoo_update_cmd()
        if cmd not in operations.get(run_click_hook, []):
            operations.setdefault(run_click_hook, []).append(cmd)
        yaml.update_yml_file(self.path_obj, data)

    def _make_click_odoo_update_cmd(self):
        return "click-odoo-update"

    def get_migration_file_modules(self):
        """Read the migration.yml and get module list."""
        content = self.load()
        modules = set()
        for version in range(len(content["migration"]["versions"])):
            try:
                migration_version = content["migration"]["versions"][version]
                modules.update(migration_version["addons"]["upgrade"])
            except KeyError:
                pass
        return modules
