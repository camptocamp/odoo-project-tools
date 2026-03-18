# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time
from collections import namedtuple
from subprocess import PIPE, Popen

from . import os_exec

SHARED_C2C_FOLDER_PREFIX = "Shared-C2C-Odoo-External/"

LastpassEntry = namedtuple("LastpassEntry", "path location name username comment")


def make_lastpass_entry(env, project, shortname, username="", location="", comment=""):
    """Create a LastpassEntry namedtuple."""
    name = f"[odoo-{env}] {shortname}"
    return LastpassEntry(
        path=f"{SHARED_C2C_FOLDER_PREFIX}{project}/{name}",
        location=location,
        name=name,
        username=username,
        comment=comment,
    )


def format_lastpass_entry(entry, password):
    """Format a LastpassEntry for display or CLI input."""
    # This is the format expected by the lastpass CLI, do not change
    return (
        f"Name: {entry.path}\n"
        f"URL: {entry.location}\n"
        f"Username: {entry.username}\n"
        f"Password: {password}\n"
        f"Notes:\n{entry.comment}\n"
    )


def store_password_in_lastpass(entry, password):
    """Store password in LastPass using the lpass CLI.

    :raises RuntimeError: if lpass is not installed or the command fails.
    :returns: True on success.
    """
    if not os_exec.has_exec("lpass"):
        raise RuntimeError(
            "LastPass CLI is not available. Please create the entry manually."
        )
    command = ["lpass", "add", "--non-interactive", entry.path]
    env = os_exec.get_venv()
    process = Popen(command, env=env, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    input_data = format_lastpass_entry(entry, password)
    out, err = process.communicate(input_data.encode("utf-8"))
    if process.returncode != 0:  # pragma: no cover
        raise RuntimeError(
            "Error storing in LastPass, please create the entry manually.\n"
            f"{out.decode()}\n{err.decode()}"
        )
    # Explicit sync + wait to avoid corrupting the local lpass cache
    # when multiple entries are stored consecutively.
    os_exec.run("lpass sync", check=True)
    time.sleep(1)
    return True
