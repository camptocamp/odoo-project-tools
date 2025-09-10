# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def get_venv():
    """Return an environment that includes the virtualenv in the PATH

    When running otools from a virtualenv, where dependencies console scripts
    might not have been installed globally, we need make sure the PATH is set
    correctly so that the executables are found.
    """
    env_PATH = os.getenv("PATH")
    # If PATH is not set, we're likely running the tests
    if not env_PATH:
        return os.environ
    bin_path = Path(sys.executable).parent
    # If the bin_path is already there, perhaps this is a global install
    if str(bin_path) in env_PATH:
        return os.environ
    # Return a copy of the environment, with the venv bin path prepended to PATH
    env = os.environ.copy()
    env["PATH"] = f"{bin_path}:{env_PATH}"
    return env


def run(cmd, drop_trailing_spaces=True, check=False, with_env=None):
    """Execute system commands and return output.

    :param cmd: the command to execute, as a string or a preparsed list
    :param drop_trailing_eol: remove trailing end-of-line chars or other wrapping spaces.
    :param with_env: a dictionary of environment variables to set, or None.
    """
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    env = get_venv()
    if with_env:
        env.update(with_env)
    res = subprocess.run(cmd, capture_output=True, env=env, check=check)
    if res.stdout is None:
        output = ""
    else:
        output = res.stdout.decode()
    if drop_trailing_spaces:
        output = output.strip()
    return output


def has_exec(name):
    return bool(shutil.which(name))
