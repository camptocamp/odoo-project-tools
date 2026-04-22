# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

"""Enforce a minimum odoo-tools version per project.

Projects can declare ``otools_min_version`` in ``.proj.cfg``. When the
installed ``odoo-tools`` is older, every ``otools-*`` command refuses
to run and prints the required version together with the upgrade
command for the detected install layout.
"""

from functools import wraps

import click
from packaging.version import Version

from .. import __version__
from ..exceptions import ProjectConfigException, ProjectRootFolderNotFound
from .config import config
from .update_check import upgrade_command


def check_minimum_version() -> None:
    """Raise ``click.ClickException`` if the installed version is too old.

    No-op when there is no reachable ``.proj.cfg`` (running outside a
    project, or before ``otools-project init``) or when the project
    does not set ``otools_min_version``.
    """
    try:
        minimum = config.otools_min_version
    except (ProjectConfigException, ProjectRootFolderNotFound):
        return
    if not minimum:
        return
    if Version(__version__) >= Version(minimum):
        return
    raise click.ClickException(
        f"This project requires odoo-tools {minimum} or newer, "
        f"but {__version__} is installed.\n"
        f"  Update with: {upgrade_command()}"
    )


def with_minimum_version_check(func):
    """Decorator: enforce ``otools_min_version`` before running the callback.

    Click's ``--help`` and ``--version`` are eager and exit before the
    callback runs, so they are naturally exempt from the check.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        check_minimum_version()
        return func(*args, **kwargs)

    return wrapper
