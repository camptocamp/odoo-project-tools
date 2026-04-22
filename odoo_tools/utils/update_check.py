# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

"""Check GitHub Releases for a newer version of odoo-tools.

The check runs at most once every 24 hours — the result is cached on disk.
Failures (network error, rate limit, bad response) are swallowed so they
never interrupt the user's command.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import click
import requests
from packaging.version import InvalidVersion, Version

from .. import __version__
from .misc import get_cache_path

logger = logging.getLogger(__name__)

REPO = "camptocamp/odoo-project-tools"
REPO_URL = f"https://github.com/{REPO}"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
CACHE_FILE_NAME = "update-check.json"
CHECK_INTERVAL = timedelta(hours=24)
FETCH_TIMEOUT = 2.0
SKIP_ENV_VAR = "OTOOLS_SKIP_UPDATE_CHECK"


def _fetch_latest_version() -> str | None:
    try:
        response = requests.get(RELEASES_URL, timeout=FETCH_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.debug("Failed to fetch latest odoo-tools version: %s", exc)
        return None
    tag = data.get("tag_name")
    if not tag:
        return None
    return tag.removeprefix("v")


def get_latest_version() -> str | None:
    """Return the latest released version, reading from the 24h cache when fresh."""
    path = get_cache_path() / CACHE_FILE_NAME
    try:
        cached = json.loads(path.read_text())
        checked_at = datetime.fromisoformat(cached["checked_at"])
        if datetime.now() - checked_at < CHECK_INTERVAL:
            return cached["latest_version"]
    except (OSError, ValueError, KeyError) as exc:
        logger.debug("Cannot read update-check cache: %s", exc)
    latest = _fetch_latest_version()
    if latest:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "checked_at": datetime.now().isoformat(),
                        "latest_version": latest,
                    }
                )
            )
        except OSError as exc:
            logger.debug("Cannot write update-check cache: %s", exc)
    return latest


def _compare(current: str, latest: str) -> bool:
    """Return True if `latest` is strictly greater than `current`."""
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return False


def upgrade_command(prefix: str | None = None) -> str:
    """Return the best-guess upgrade command for the current install layout."""
    prefix = prefix or sys.prefix
    parts = Path(prefix).parts
    if "pipx" in parts:
        return "pipx upgrade odoo-tools"
    # uv tool installs live under ".../uv/tools/<pkg>/..."
    if "uv/tools" in Path(prefix).as_posix():
        return "uv tool upgrade odoo-tools"
    return f"pip install --upgrade git+{REPO_URL}"


def check_for_update() -> None:
    """Warn the user on stderr if a newer release is available.

    Never raises. Honors ``OTOOLS_SKIP_UPDATE_CHECK`` to opt out entirely.
    """
    if os.getenv(SKIP_ENV_VAR):
        return
    latest = get_latest_version()
    if not latest or not _compare(__version__, latest):
        return
    click.secho(
        f"A new version of odoo-tools is available: {latest} "
        f"(installed: {__version__})\n"
        f"  Update with: {upgrade_command()}",
        fg="yellow",
        err=True,
    )


def with_update_check(func):
    """Decorator for click group/command callbacks: run ``check_for_update`` first.

    Click's eager ``--help`` and ``--version`` exit before the callback runs,
    so the check is naturally skipped for those flags.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        check_for_update()
        return func(*args, **kwargs)

    return wrapper
