# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import subprocess
from collections.abc import Iterator
from functools import cache
from os import PathLike
from pathlib import Path
from typing import NamedTuple

from git.config import GitConfigParser
from git_autoshare.core import find_autoshare_repository

from . import ui
from .config import config as proj_config
from .os_exec import run
from .path import build_path, cd, root_path
from .proj import get_odoo_version, get_project_id


def _repo_name_from_url(url: str) -> str:
    """Extract repository name from a GitHub SSH or HTTPS URL."""
    return url.rstrip("/").split("/")[-1].removesuffix(".git")


def remote_exists(git_dir: str | Path, remote_name: str) -> bool:
    """Return True if the named remote exists in the repo at git_dir."""
    result = subprocess.run(
        ["git", "-C", str(git_dir), "remote", "get-url", remote_name],
        capture_output=True,
    )
    return result.returncode == 0


@cache
def remote_repo_exists(url: str) -> bool:
    """Return True if the github repository at ``url`` is reachable.

    Used to avoid registering a remote that points to a non-existent repository.
    A dangling remote breaks git's fallback ``fetch --all`` with
    ``Repository not found``, which is exactly what registering targeted remotes
    is meant to prevent.

    Results are cached because ``setup_submodule_remotes`` is called twice per
    submodule (autoshare cache and working tree), so the network probe would
    otherwise be repeated.
    """
    result = subprocess.run(["git", "ls-remote", url], capture_output=True)
    return result.returncode == 0


def ensure_remote(git_dir: str | Path, remote_name: str, url: str) -> bool:
    """Add a named remote if it doesn't already exist.

    Returns True if the remote was added, False if it was already present.
    """
    if remote_exists(git_dir, remote_name):
        return False
    run(
        ["git", "-C", str(git_dir), "remote", "add", remote_name, url],
        check=True,
    )
    return True


def fetch_targeted(git_dir: str | Path, remote_name: str, refspec: str) -> None:
    """Fetch a single refspec from a named remote, emitting a warning on failure."""
    try:
        run(
            ["git", "-C", str(git_dir), "fetch", remote_name, refspec],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        ui.echo(
            f"WARNING: fetch {remote_name} {refspec} in {git_dir} failed: {e}",
            fg="yellow",
        )


def setup_submodule_remotes(
    repo_path: str | Path,
    submodule_url: str,
    base_branch: str,
    project_id: str | None,
    company_remote: str,
) -> None:
    """Ensure OCA and <company_remote> (e.g. camptocamp) remotes exist and fetch targeted branches.

    Fetch strategy:
      OCA              -> base branch only (e.g. refs/heads/18.0)
      <company_remote> -> merge-branch-<project_id>-* only (skipped when project_id is None)

    A remote is only added when the corresponding github repository actually
    exists. Many submodules are not OCA repositories (e.g. private
    ``<company_remote>/...`` modules), so blindly adding an ``OCA/<repo>`` remote
    would point at a non-existent repository and break git's fallback fetch.

    The (network) existence probe is skipped when the remote is already
    configured locally: an existing remote is trusted and only re-fetched.

    Safe to call on both submodule working trees and autoshare bare caches.
    """
    repo_name = _repo_name_from_url(submodule_url)
    oca_url = f"git@github.com:OCA/{repo_name}.git"
    c2c_url = f"git@github.com:{company_remote}/{repo_name}.git"

    if remote_exists(repo_path, "OCA") or remote_repo_exists(oca_url):
        ensure_remote(repo_path, "OCA", oca_url)
        fetch_targeted(
            repo_path,
            "OCA",
            f"+refs/heads/{base_branch}:refs/remotes/OCA/{base_branch}",
        )

    if project_id and (
        remote_exists(repo_path, company_remote) or remote_repo_exists(c2c_url)
    ):
        ensure_remote(repo_path, company_remote, c2c_url)
        fetch_targeted(
            repo_path,
            company_remote,
            f"+refs/heads/merge-branch-{project_id}-*"
            f":refs/remotes/{company_remote}/merge-branch-{project_id}-*",
        )


def get_pinned_sha(submodule_path: str | PathLike) -> str | None:
    """Return the commit SHA recorded in the parent repo HEAD for this submodule."""
    try:
        output = run(["git", "ls-tree", "HEAD", str(submodule_path)], check=True)
        if output:
            # "160000 commit <sha>\t<path>"
            parts = output.split()
            if len(parts) >= 3:
                return parts[2]
    except (subprocess.CalledProcessError, IndexError):
        pass
    return None


def pin_submodule_commit(repo_path: str | Path, pinned_sha: str) -> bool:
    """Create refs/c2c-sync/pinned pointing to pinned_sha to prevent fallback fetches.

    When a commit exists in the object store via alternates but is not pointed
    to by any local ref, git's fallback fetch tries all alternate-repo remotes —
    including a parent repo's 'me' remote — via blocked file:// transport.
    Pinning a local ref makes the commit reachable from --all so the fallback
    never triggers.

    Returns True if the ref was set, False if the commit is not in the object store.
    """
    check = subprocess.run(
        ["git", "-C", str(repo_path), "cat-file", "-e", f"{pinned_sha}^{{commit}}"],
        capture_output=True,
    )
    if check.returncode != 0:
        return False
    run(
        [
            "git",
            "-C",
            str(repo_path),
            "update-ref",
            "refs/c2c-sync/pinned",
            pinned_sha,
        ],
        check=True,
    )
    return True


class SubmoduleInfo(NamedTuple):
    path: str
    url: str
    branch: str | None
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
    filter_path: str | PathLike | None = None,
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


def submodule_sync(path: str | PathLike):
    """Submodule sync"""
    sync_cmd = ["git", "submodule", "sync"]
    if path:
        sync_cmd += ["--", str(path)]
    run(sync_cmd, check=True)


def submodule_update(path: str | PathLike):
    """Submodule update"""
    cmd = ["git", "submodule", "update", "--init"]
    args = []
    # Use git-autoshare if available
    submodule = next(iter_gitmodules(filter_path=path), None)
    project_id: str | None = None
    base_branch: str = get_odoo_version()
    company_remote = proj_config.company_git_remote
    if submodule:
        ui.echo(f"Updating submodule {submodule.path}")
        project_id = get_project_id(raise_if_missing=False)
        base_branch = submodule.branch or base_branch
        __, autoshare_repo = find_autoshare_repository([submodule.url])
        if autoshare_repo:
            if not Path(autoshare_repo.repo_dir).exists():
                autoshare_repo.prefetch(True)
            # Populate the autoshare cache with targeted OCA/<company_remote> refs so
            # that the recorded commit is reachable from a named ref in the cache.
            # This prevents git's fallback fetch from reaching parent-repo remotes
            # (including any 'me' remote) via blocked file:// transport.
            setup_submodule_remotes(
                autoshare_repo.repo_dir,
                submodule.url,
                base_branch,
                project_id,
                company_remote,
            )
            args += ["--reference", autoshare_repo.repo_dir]
        else:
            ui.echo(
                f"Auto-share conf not found for {submodule.url}. You may want to check your auto-share configuration."
            )
    args.append(str(path))
    run(cmd + args, check=True)
    # After the submodule is updated: ensure it has OCA/<company_remote> remotes and
    # pin the recorded commit so subsequent git operations never trigger the
    # fallback fetch path.
    if submodule and Path(build_path(submodule.path)).exists():
        setup_submodule_remotes(
            build_path(submodule.path),
            submodule.url,
            base_branch,
            project_id,
            company_remote,
        )
        pinned_sha = get_pinned_sha(submodule.path)
        if pinned_sha:
            pin_submodule_commit(build_path(submodule.path), pinned_sha)


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
    """Return the current branch name, or None when not on a branch."""
    try:
        return run(["git", "branch", "--show-current"], check=True) or None
    except subprocess.CalledProcessError:
        return None


def tag_signing_enabled(repo):
    """Return True if git is configured to sign tags.

    ``tag.gpgsign`` is authoritative when set (so an explicit ``false`` disables
    signing even if a signing key exists); otherwise we fall back to the
    presence of a ``user.signingkey``.
    """
    with repo.config_reader() as reader:
        try:
            return bool(reader.get_value("tag", "gpgsign"))
        except Exception:
            pass
        try:
            return bool(reader.get_value("user", "signingkey"))
        except Exception:
            return False


def delete_branch(branch_name):
    run(["git", "branch", "-D", branch_name])


def get_submodule_commit(path):
    """Return the current HEAD commit of a submodule, or None on error."""
    abs_path = str(build_path(path))
    try:
        return run(["git", "-C", abs_path, "rev-parse", "HEAD"])
    except subprocess.CalledProcessError:
        return None


def submodule_upgrade(path, url, branch=None):
    """Upgrade a submodule to the latest remote commit.

    :param path: submodule path (relative to project root)
    :param url: submodule remote url
    :param branch: if set, force checkout of this specific branch
    :returns: True if the submodule was upgraded, False otherwise
    """
    commit_before = get_submodule_commit(path)
    abs_path = str(build_path(path))
    if branch:
        run(["git", "-C", abs_path, "reset", "HEAD", "--hard"], check=True)
        run(["git", "-C", abs_path, "fetch", url], check=True)
        run(["git", "-C", abs_path, "checkout", branch], check=True)
    else:
        cmd = ["git", "submodule", "update", "-f", "--remote", "--checkout"]
        # Use git-autoshare if available
        submodule = next(iter_gitmodules(filter_path=path), None)
        if submodule:
            __, autoshare_repo = find_autoshare_repository([submodule.url])
            if autoshare_repo and Path(autoshare_repo.repo_dir).exists():
                cmd += ["--reference", autoshare_repo.repo_dir]
        cmd.append(str(path))
        run(cmd, check=True)
    commit_after = get_submodule_commit(path)
    if commit_before != commit_after:
        ui.echo(f"UPGRADED {path}: {commit_before} -> {commit_after}")
        return True
    else:
        ui.echo(f"NOT UPGRADED {path}: already up to date ({commit_before})")
        return False
