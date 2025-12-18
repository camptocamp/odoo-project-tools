# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import subprocess
from collections.abc import Iterator
from os import PathLike
from pathlib import Path
from typing import NamedTuple, Optional, Union

from git.config import GitConfigParser
from git_autoshare.core import find_autoshare_repository

from . import ui
from .os_exec import run
from .path import build_path, cd, root_path


class SubmoduleInfo(NamedTuple):
    path: str
    url: str
    branch: Optional[str]
    exists: bool
    cloned: bool


def get_odoo_core(hash, dest="src/odoo", org="odoo"):
    _checkout_repo(org, "odoo", build_path(dest), hash)


def get_odoo_enterprise(hash, dest="src/enterprise", org="odoo"):
    _checkout_repo(org, "enterprise", build_path(dest), hash)


def _checkout_repo(org, repo, dest, ref, depth=None):
    repo_url = f"git@github.com:{org}/{repo}"
    __, autoshare_repo = find_autoshare_repository([repo_url])
    dest = Path(dest)
    # If the repository doesn't exist, clone it (without checkout)
    if not (dest / ".git").is_dir():
        ui.echo(f"Cloning {org}/{repo} on {ref}, be patient..")
        if autoshare_repo:
            command = "autoshare-clone"
        else:
            command = "clone"
        args = [
            "--quiet",
            "--no-checkout",
        ]
        if depth:
            args.extend(["--depth", str(depth)])
        args.extend([repo_url, str(dest)])
        subprocess.run(["git", command, *args], check=True)
    # Fetch the ref to checkout
    ui.echo(f"Fetching {org}/{repo} {ref}")
    args = ["--quiet"]
    if depth:
        args.extend(["--depth", str(depth)])
    args.extend(["origin", ref])
    subprocess.run(["git", "-C", str(dest), "fetch", *args], check=True)
    # Checkout
    ui.echo(f"Checking out {org}/{repo} {ref}..")
    git_args = [
        "-C",
        str(dest),
        "-c",
        "advice.detachedHead=false",
    ]
    subprocess.run(["git", *git_args, "checkout", "--force", ref], check=True)


def _get_gitmodules():
    return build_path(".gitmodules")


def iter_gitmodules(
    filter_path: Optional[Union[str, PathLike]] = None,
) -> Iterator[SubmoduleInfo]:
    """Yields the submodules from `.gitmodules`

    :param filter_path: if provided, only yield the submodules on the given path
    """
    config = GitConfigParser(str(_get_gitmodules()), read_only=True)
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
    run(sync_cmd, check=True)


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
            if not Path(autoshare_repo.repo_dir).exists():
                autoshare_repo.prefetch(True)
            args += ["--reference", autoshare_repo.repo_dir]
    args.append(str(path))
    run(cmd + args, check=True)


def submodule_set_url(repo_path, url, remote="origin"):
    with cd(root_path()):
        run(
            ["git", "config", "--file=.gitmodules", f"submodule.{repo_path}.url", url],
            check=True,
        )


def set_remote_url(repo_path, url, remote="origin", add=False):
    submodule_set_url(repo_path, url, remote=remote)
    cmd = ["git", "remote", "set-url", remote, url]
    if add:
        cmd = ["git", "remote", "add", remote, url]
    with cd(build_path(repo_path)):
        run(cmd, check=True)


def checkout(branch_name, remote="origin"):
    run(["git", "fetch", remote, branch_name])
    run(["git", "checkout", f"{remote}/{branch_name}"])


def get_current_branch():
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        branch = None
    return branch


def delete_branch(branch_name):
    run(["git", "branch", "-D", branch_name])
