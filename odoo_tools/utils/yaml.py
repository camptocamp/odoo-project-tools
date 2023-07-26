# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

# TODO: do we really need this to edit such files?
from ruamel.yaml import YAML

yaml = YAML()


def yaml_load(stream):
    return yaml.load(stream)


def yaml_dump(data, fileob):
    yaml.dump(data, fileob)


def update_yml_file(path, new_data, main_key=None):
    # preservation of indentation
    yaml.indent(mapping=2, sequence=4, offset=2)

    with open(path) as f:
        data = yaml_load(f.read()) or {}
        if main_key:
            data[main_key].update(new_data)
        else:
            data.update(new_data)

    with open(path, "w") as f:
        yaml.dump(data, f)
