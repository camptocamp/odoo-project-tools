# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from ..exceptions import Exit


def exit_msg(msg):
    raise Exit(msg)


def ask_confirmation(message):
    """Gently ask user's opinion."""
    r = input(message + " (y/N) ")
    return r in ("y", "Y", "yes")


def ask_or_abort(message):
    """Fail (abort) immediately if user disagrees."""
    if not ask_confirmation(message):
        exit_msg("Aborted")


def echo(msg):
    click.echo(msg)
