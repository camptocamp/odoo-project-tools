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
        yield SubmoduleInfo(info["path"], info["url"], info.get("branch"))


def submodule_add(
    url: str,
    path: Union[str, PathLike],
    branch: Optional[str] = None,
) -> None:
    """Add a submodule"""
    cmd = ["git", "autoshare-submodule-add"]
    args = ["--force", url, str(path)]
    if branch:
        args = ["-b", branch, *args]
    subprocess.run(cmd + args, check=True)


def _get_submodules(submodule_path=None):
    """return a list of (submodule path, submodule url).
    If a submodule path is passed as argument, only submodules with that path are returned
    """

    output = subprocess.run(
        ["git", "config", "--file", _get_gitmodules(), "--get-regexp", "path"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    paths = [line.split()[1] for line in output.splitlines()]

    output = subprocess.run(
        ["git", "config", "--file", _get_gitmodules(), "--get-regexp", "url"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    urls = [line.split()[1] for line in output.splitlines()]
    module_list = zip(
        paths,
        urls,
        # strict=True
    )

    if submodule_path is not None:
        submodule_path = os.path.normpath(submodule_path)
        module_list = [
            (path, url)
            for path, url in module_list
            if os.path.normpath(path) == submodule_path
        ]
    return module_list


def submodule_sync(submodule_path=None):
    sync_cmd = ["git", "submodule", "sync"]

    if submodule_path:
        sync_cmd += ["--", submodule_path]

    subprocess.run(sync_cmd, check=True)


def submodule_update(submodule_info):
    """
    :param submodule_info: list of (submodule path, submodule url), as returned by `_get_submodules()`
    """
    base_update_cmd = ["git", "submodule", "update", "--init"]

    for path, url in submodule_info:
        args = []
        if AUTOSHARE_ENABLED:
            index, autoshare_repo = find_autoshare_repository([url])
            if autoshare_repo:
                if not os.path.exists(autoshare_repo.repo_dir):
                    autoshare_repo.prefetch(True)
                args += ["--reference", autoshare_repo.repo_dir]
        args.append(path)
        subprocess.run(base_update_cmd + args, check=True)


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
