# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import subprocess

from . import ui
from .path import build_path


def get_odoo_core(hash, dest="src/odoo", org="odoo", branch=None):
    dest = build_path(dest)
    _clone_or_fetch_repo(org, "odoo", branch, dest)
    ui.echo(f"Checking out {hash}")
    subprocess.run(["git", "-C", dest, "checkout", hash], check=True)


def get_odoo_enterprise(hash, dest="src/enterprise", org="odoo", branch=None):
    dest = build_path(dest)
    _clone_or_fetch_repo(org, "enterprise", branch, dest)
    ui.echo(f"Checking out {hash}")
    subprocess.run(["git", "-C", dest, "checkout", hash])


def _clone_or_fetch_repo(org, repo, branch, dest):
    # TODO: use git-autoshare clone
    if os.path.isdir(os.path.join(dest, ".git")):
        ui.echo(f"Fetching {org}/{repo} {branch}")
        subprocess.run(["git", "-C", dest, "fetch", "--quiet", "--all"], check=True)
    else:
        ui.echo(f"Cloning {org}/{repo} on branch {branch}, be patient")
        subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--branch",
                branch,
                f"git@github.com:{org}/{repo}",
                dest,
            ],
            check=True,
        )
