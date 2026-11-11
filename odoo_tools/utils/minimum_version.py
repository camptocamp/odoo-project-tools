# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

"""Enforce a minimum odoo-tools version per project.

Projects can declare ``otools_min_version`` in their configuration. When the
installed ``odoo-tools`` is older, every ``otools-*`` command refuses
to run and prints the required version together with the upgrade
command for the detected install layout.
"""

from functools import wraps

import click
from packaging.version import InvalidVersion, Version

from .. import __version__
from ..exceptions import ProjectConfigException, ProjectRootFolderNotFound
from .config import config, read_config_sources
from .update_check import upgrade_command


def _read_unvalidated_minimum_version() -> str | None:
    """Read ``otools_min_version`` from a configuration that does not validate.

    Whatever else is wrong with the configuration, an outdated odoo-tools must
    not get past the check: it may be the very reason the configuration does
    not validate, e.g. a setting this version does not know about yet.
    """
    try:
        settings, __ = read_config_sources()
    except ProjectConfigException:
        return None
    minimum = settings.get("otools_min_version")
    if not minimum:
        return None
    try:
        Version(str(minimum))
    except InvalidVersion:
        return None
    return str(minimum)


def check_minimum_version() -> None:
    """Raise ``click.ClickException`` if the installed version is too old.

    No-op when running outside a project, when its configuration cannot be
    read, or when the project does not set a valid ``otools_min_version``.
    """
    try:
        minimum = config.otools_min_version
    except ProjectRootFolderNotFound:
        return
    except ProjectConfigException:
        minimum = _read_unvalidated_minimum_version()
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
