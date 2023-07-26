# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from pathlib import PosixPath

from .utils.misc import parse_ini_cfg
from .utils.path import build_path

# TODO: use this as marker file
PROJ_CFG_FILE = os.getenv("PROJ_CFG_FILE", ".proj.cfg")


# TODO
# @lru_cache(maxsize=None)
def read_conf():
    with open(build_path(PROJ_CFG_FILE)) as fd:
        return dict(parse_ini_cfg(fd.read(), "conf")["conf"])


def get_conf_key(key):
    conf = read_conf()
    v = conf.get(key)
    if key.endswith("_path"):
        v = PosixPath(v)
    return v
