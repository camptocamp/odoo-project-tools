# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os

import click
from rich.console import Console

from ..exceptions import Exit

# Rich console writing to stderr, for warnings/diagnostics that must not be
# mixed with a command's stdout (e.g. JSON output or a live-rendered table).
err_console = Console(stderr=True)


def exit_msg(msg):
    raise Exit(msg)


def warn_missing_github_token():
    """Warn (on stderr) when no GITHUB_TOKEN is set.

    Unauthenticated GitHub API requests share a low rate limit and quickly
    start failing; commands that hit the API should call this up front.
    """
    if not os.environ.get("GITHUB_TOKEN"):
        err_console.print(
            "Warning: GITHUB_TOKEN is not set; GitHub API requests "
            "are unauthenticated and may hit rate limits.",
            style="yellow",
        )


def ask_confirmation(message):
    """Gently ask user's opinion."""
    r = input(message + " (y/N) ")
    return r in ("y", "Y", "yes")


def ask_or_abort(message):
    """Fail (abort) immediately if user disagrees."""
    if not ask_confirmation(message):
        exit_msg("Aborted")


def echo(msg, *pa, **kw):
    cmd = click.echo
    if kw.get("fg"):
        cmd = click.secho
    cmd(msg, *pa, **kw)


def ask_question(message, **prompt_kwargs):
    """Ask a question and return the answer

    Wrapper around ``click.prompt()``
    """
    return click.prompt(message, **prompt_kwargs)
