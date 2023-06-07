# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import shlex
import shutil
import subprocess


def run(cmd, drop_trailing_spaces=True):
    """Execute system commands and return output.

    :param cmd: the command to execute
    :param drop_trailing_eol: remove trailing end-of-line chars or other wrapping spaces.
    """
    res = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE)
    output = res.stdout.decode()
    if drop_trailing_spaces:
        output = output.strip()
    return output


def has_exec(name):
    return bool(shutil.which(name))
