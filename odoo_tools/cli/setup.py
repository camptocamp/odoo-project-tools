# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""otools-setup — post-install configuration helper.

This command group is intentionally extensible: new setup actions should be
added as subcommands here rather than as standalone entry points.
"""

from __future__ import annotations

import shutil

import click

from ..utils.click import global_command_decorators
from ..utils.completion import (
    SHELLS,
    detect_shell,
    diff_rc_content,
    fish_completions_dir,
    installed_completions_dir,
    shell_rc_file,
    update_rc_content,
)


@click.group()
@global_command_decorators
def cli():
    """Post-install setup for odoo-tools."""


@cli.command("shell-completion")
@click.option(
    "--shell",
    "shell_name",
    default=None,
    type=click.Choice(SHELLS),
    help="Target shell.  Defaults to the value of the SHELL environment variable.",
)
def shell_completion(shell_name: str | None) -> None:
    """Configure shell completion for all otools-* commands.

    Detects your shell, resolves the installed completion directory, and
    updates your shell startup file with the required snippet.  The proposed
    change is shown before anything is written so you can review it first.

    For fish the completion files are copied to ~/.config/fish/completions/;
    no RC-file edit is needed.
    """
    # --- shell detection ---------------------------------------------------
    if shell_name is None:
        shell_name = detect_shell()
        if shell_name is None:
            raise click.ClickException(
                "Could not detect your shell from $SHELL.  "
                "Pass --shell <bash|zsh|fish> explicitly."
            )
        click.echo(f"Detected shell: {shell_name}")

    completions_dir = installed_completions_dir()

    # --- fish: copy files, no RC edit needed --------------------------------
    if shell_name == "fish":
        _setup_fish(completions_dir)
        return

    # --- bash / zsh: update RC file ----------------------------------------
    rc_path = shell_rc_file(shell_name)
    assert rc_path is not None  # guaranteed for bash/zsh

    existing = rc_path.read_text() if rc_path.exists() else ""
    updated = update_rc_content(existing, shell_name, completions_dir)

    if existing == updated:
        click.echo(f"{rc_path} is already up to date.  Nothing to do.")
        return

    diff = diff_rc_content(existing, updated, rc_path)
    click.echo(f"\nProposed changes to {rc_path}:\n")
    click.echo(diff)

    if not click.confirm("Apply these changes?"):
        raise click.Abort()

    rc_path.write_text(updated)
    click.echo(f"Updated {rc_path}.")
    click.echo("Reload your shell (e.g. `source {rc_path}`) to activate completion.")


def _setup_fish(completions_dir):
    """Copy fish completion files to the fish completions directory."""
    fish_dir = fish_completions_dir()
    fish_dir.mkdir(parents=True, exist_ok=True)
    source_dir = completions_dir / "fish"
    if not source_dir.exists():
        raise click.ClickException(f"Fish completion sources not found at {source_dir}")

    fish_files = list(source_dir.glob("*.fish"))
    if not fish_files:
        raise click.ClickException(f"No .fish completion files found in {source_dir}")

    click.echo(f"Will copy {len(fish_files)} file(s) to {fish_dir}:\n")
    for f in sorted(fish_files):
        click.echo(f"  {f.name}")

    click.echo()
    if not click.confirm("Apply?"):
        raise click.Abort()

    for f in fish_files:
        shutil.copy2(f, fish_dir / f.name)

    click.echo(f"Copied {len(fish_files)} completion file(s) to {fish_dir}.")
    click.echo("Open a new fish session (or run `exec fish`) to activate completion.")


if __name__ == "__main__":
    cli()
