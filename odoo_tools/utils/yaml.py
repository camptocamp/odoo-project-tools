# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path

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

    yml_path = Path(path)
    data = yaml_load(yml_path.read_text()) or {}
    if main_key:
        data[main_key].update(new_data)
    else:
        data.update(new_data)

    with yml_path.open("w") as fobj:
        yaml.dump(data, fobj)
