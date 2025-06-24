# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import shlex
import shutil
import subprocess
import sys


def get_venv():
    """Return an environment that includes the virtualenv in the PATH

    When running otools from a virtualenv, where dependencies console scripts
    might not have been installed globally, we need make sure the PATH is set
    correctly so that the executables are found.
    """
    # If PATH is not set, we're likely running the tests
    if not os.environ.get("PATH"):
        return os.environ
    bin_path = os.path.dirname(sys.executable)
    # If the bin_path is already there, perhaps this is a global install
    if bin_path in os.environ["PATH"]:
        return os.environ
    # Return a copy of the environment, with the venv bin path prepended to PATH
    env = os.environ.copy()
    env["PATH"] = f"{bin_path}:{env['PATH']}"
    return env


def run(cmd, drop_trailing_spaces=True, check=False):
    """Execute system commands and return output.

    :param cmd: the command to execute, as a string or a preparsed list
    :param drop_trailing_eol: remove trailing end-of-line chars or other wrapping spaces.
    """
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, env=get_venv(), check=check)
    if res.stdout is None:
        output = ""
    else:
        output = res.stdout.decode()
    if drop_trailing_spaces:
        output = output.strip()
    return output


def has_exec(name):
    return bool(shutil.which(name))
