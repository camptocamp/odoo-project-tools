# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import subprocess
from collections.abc import Iterator
from os import PathLike
from pathlib import Path
from typing import NamedTuple, Optional, Union

from git.config import GitConfigParser
from git_autoshare.core import find_autoshare_repository

from . import ui
from .path import build_path, cd


class SubmoduleInfo(NamedTuple):
    path: str
    url: str
    branch: Optional[str]
    exists: bool
    cloned: bool


def get_odoo_core(hash, dest="src/odoo", org="odoo", branch=None):
    dest = str(build_path(dest))
    _clone_or_fetch_repo(org, "odoo", branch, dest)
    ui.echo(f"Checking out {hash}")
    subprocess.run(["git", "-C", dest, "checkout", hash], check=True)


def get_odoo_enterprise(hash, dest="src/enterprise", org="odoo", branch=None):
    dest = str(build_path(dest))
    _clone_or_fetch_repo(org, "enterprise", branch, dest)
    ui.echo(f"Checking out {hash}")
    subprocess.run(["git", "-C", dest, "checkout", hash], check=False)


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


def _get_gitmodules():
    return str(build_path(".gitmodules"))


def iter_gitmodules(
    filter_path: Optional[Union[str, PathLike]] = None,
) -> Iterator[SubmoduleInfo]:
    """Yields the submodules from `.gitmodules`

    :param filter_path: if provided, only yield the submodules on the given path
    """
    config = GitConfigParser(_get_gitmodules(), read_only=True)
    if filter_path:
        filter_path = Path(filter_path)
    for section in config.sections():
        info = dict(config.items(section))
        assert "path" in info, f"Missing `path` in {section}"
        assert "url" in info, f"Missing `url` in {section}"
        if filter_path and not Path(info["path"]).is_relative_to(filter_path):
            continue
        path = Path(build_path(info["path"]))
        exists = path.exists()
        cloned = exists and Path(path / ".git").exists()
        yield SubmoduleInfo(
            info["path"], info["url"], info.get("branch"), exists, cloned
        )


def submodule_init(submodule: SubmoduleInfo) -> None:
    """Add a submodule"""
    if submodule.exists:
        submodule_update(submodule.path)
    else:
        submodule_add(submodule)


def submodule_add(submodule: SubmoduleInfo) -> None:
    """Add a submodule"""
    cmd = ["git", "autoshare-submodule-add"]
    args = ["--force", submodule.url, str(submodule.path)]
    if submodule.branch:
        args = ["-b", submodule.branch, *args]
    subprocess.run(cmd + args, check=True)


def submodule_sync(path: Union[str, PathLike]):
    """Submodule sync"""
    sync_cmd = ["git", "submodule", "sync"]
    if path:
        sync_cmd += ["--", str(path)]
    subprocess.run(sync_cmd, check=True)


def submodule_update(path: Union[str, PathLike]):
    """Submodule update"""
    cmd = ["git", "submodule", "update", "--init"]
    args = []
    # Use git-autoshare if available
    submodule = next(iter_gitmodules(filter_path=path), None)
    if submodule:
        __, autoshare_repo = find_autoshare_repository([submodule.url])
        if autoshare_repo:
            ui.echo(f"Auto-share conf found for {autoshare_repo.repo_dir}")
            if not os.path.exists(autoshare_repo.repo_dir):
                autoshare_repo.prefetch(True)
            args += ["--reference", autoshare_repo.repo_dir]
    args.append(str(path))
    subprocess.run(cmd + args, check=True)


def set_remote_url(repo_path, url):
    subprocess.run(
        ["git", "config", "--file=.gitmodules", f"submodule.{repo_path}.url", url],
        check=True,
    )
    # relative_name = repo_path.relative_to("../")
    with cd(build_path(repo_path)):
        subprocess.run(["git", "remote", "set-url", "origin", url], check=True)


def checkout(branch_name):
    subprocess.run(["git", "fetch", "origin", branch_name])
    subprocess.run(["git", "checkout", f"origin/{branch_name}"])
