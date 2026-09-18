# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import subprocess
import threading
from collections.abc import Iterator
from functools import cache
from os import PathLike
from pathlib import Path
from typing import NamedTuple

from git.config import GitConfigParser
from git_autoshare.core import config as autoshare_config
from git_autoshare.core import find_autoshare_repository

from . import ui
from .config import config as proj_config
from .os_exec import run
from .path import build_path, root_path
from .proj import get_odoo_version, get_project_id, get_project_manifest

_superproject_lock = threading.Lock()


def run_in_superproject(cmd, **kwargs):
    """Run a git command that writes files the whole superproject shares.

    ``.gitmodules``, ``.git/config`` and ``.git/index`` belong to the project
    repository rather than to any one submodule, and git guards each of them
    with a lock file it never waits on: a second writer fails outright with
    ``Unable to create '....lock': File exists``. So these run one at a time.

    They also run *from* the project root, passed as ``cwd`` rather than
    chdir'd into: the working directory is process-global, so changing it would
    move it under the feet of whatever else is running.

    Use it for the commands that write that shared metadata, and plain
    :func:`~.os_exec.run` for the ones that only touch a single submodule --
    those are the ones that take the time, and serialising them would defeat
    handling several submodules at once.
    """
    with _superproject_lock:
        return run(cmd, cwd=root_path(), check=True, **kwargs)


def _repo_name_from_url(url: str) -> str:
    """Extract repository name from a GitHub SSH or HTTPS URL."""
    return url.rstrip("/").split("/")[-1].removesuffix(".git")


def remote_exists(git_dir: str | Path, remote_name: str) -> bool:
    """Return True if the named remote exists in the repo at git_dir.

    Quiet: not having the remote is one of the answers, so git saying so is
    not worth putting in front of anybody.
    """
    try:
        run(
            ["git", "-C", str(git_dir), "remote", "get-url", remote_name],
            check=True,
            quiet=True,
        )
    except subprocess.CalledProcessError:
        return False
    return True


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
    try:
        run(["git", "ls-remote", url], check=True, quiet=True)
    except subprocess.CalledProcessError:
        return False
    return True


def get_remotes(git_dir: str | Path) -> dict[str, str]:
    """Return the repo's remotes as a mapping of remote name to fetch URL."""
    output = run(["git", "-C", str(git_dir), "remote", "-v"], check=True)
    remotes = {}
    for line in output.splitlines():
        name, url_and_kind = line.split("\t")
        url, _, kind = url_and_kind.rpartition(" ")
        if kind == "(fetch)":
            remotes[name] = url
    return remotes


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


def get_pinned_sha(
    submodule_path: str | PathLike, cwd: str | Path | None = None
) -> str | None:
    """Return the commit SHA recorded in the parent repo HEAD for this submodule."""
    try:
        output = run(
            ["git", "ls-tree", "HEAD", str(submodule_path)], cwd=cwd, check=True
        )
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
    try:
        run(
            ["git", "-C", str(repo_path), "cat-file", "-e", f"{pinned_sha}^{{commit}}"],
            check=True,
            quiet=True,
        )
    except subprocess.CalledProcessError:
        # Not in the object store, so there is nothing to point a ref at.
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


def get_odoo_core(ref, dest="src/odoo", org="odoo"):
    _checkout_repo(org, "odoo", build_path(dest), ref)


def get_odoo_enterprise(ref, dest="src/enterprise", org="odoo"):
    _checkout_repo(org, "enterprise", build_path(dest), ref)


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
    # Check out `FETCH_HEAD` rather than `ref`: for a commit hash both are the
    # same, but a branch name would resolve to the local branch left behind by a
    # previous run instead of the revision we've just fetched.
    git_args = [
        "-C",
        str(dest),
        "-c",
        "advice.detachedHead=false",
    ]
    subprocess.run(["git", *git_args, "checkout", "--force", "FETCH_HEAD"], check=True)


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


def preload_submodule_state() -> None:
    """Fill the caches :func:`submodule_update` reads, on the calling thread.

    Each of them is computed on first use and reused afterwards -- but that
    first use has to happen before several submodules are handled at once:

    * git-autoshare ``print()``s when it cannot find its ``repos.yml``, and it
      does it in-process, where no capture can reach it. From a worker that
      line lands in the middle of the live display.
    * the project manifest is parsed with a shared YAML parser (see
      :mod:`~odoo_tools.utils.yaml`), so every worker missing the cache at once
      means doing the same parse N times, one after another, for one answer.

    Call it before fanning out. It is cheap, and doing it twice does nothing.
    """
    autoshare_config()
    get_project_manifest()
    proj_config.company_git_remote  # noqa: B018 -- a cached_property, filled by reading


def submodule_init(submodule: SubmoduleInfo) -> None:
    """Add a submodule, or bring it up to date if it is already there.

    The second case goes through :func:`submodule_update`, so the same applies:
    the submodule has to have been registered already.
    """
    if submodule.exists:
        submodule_update(submodule.path, submodule=submodule)
    else:
        submodule_add(submodule)


def prefetch_autoshare(url: str) -> None:
    """Populate the git-autoshare cache for ``url``, out of process.

    ``AutoshareRepository.prefetch()`` would do the same in-process: it prints
    and runs git on our own file descriptors, so its output goes straight to
    the terminal, past :func:`~.os_exec.capture_output` and over whatever is
    drawn there. The console script does the work in a child process, whose
    output :func:`~.os_exec.run` does capture.
    """
    run(["git", "autoshare-prefetch", "-q", url], check=True)


def submodule_add(submodule: SubmoduleInfo) -> None:
    """Add a submodule to the superproject.

    Serialised whole: ``git submodule add`` clones *and* writes ``.gitmodules``,
    the index and ``.git/config``, and it is not documented where in that
    sequence it takes which lock. So adding submodules stays sequential -- it
    is the rare path anyway, an existing checkout going through
    :func:`submodule_update`.
    """
    args = ["--force", submodule.url, str(submodule.path)]
    if submodule.branch:
        args = ["-b", submodule.branch, *args]
    # git-autoshare-submodule-add takes no -C: it shells out to `git submodule
    # add` in the working directory, hence the project root.
    run_in_superproject(["git", "autoshare-submodule-add", *args])


def sync_submodules(paths) -> None:
    """Point the submodules' remotes at the urls recorded in ``.gitmodules``.

    Every path in one command. See :func:`register_submodules` for why.
    """
    paths = [str(path) for path in paths]
    if paths:
        run_in_superproject(["git", "submodule", "sync", "--", *paths])


def register_submodules(paths) -> None:
    """Copy the submodules' urls from ``.gitmodules`` into ``.git/config``.

    The "init" half of ``git submodule update --init``, which the manual
    defines as exactly these two commands. Split out, and taking every path at
    once, because of what it costs: it writes only the superproject's shared
    metadata, so it has to be serialised, and it costs the same for thirty
    paths as for one -- around 70ms either way, nearly all of it ``git
    submodule`` start-up rather than the write itself. Left in the
    per-submodule path it would serialise 70ms times the number of submodules,
    however many workers were running, which on a large project is most of the
    time the command takes.

    So the callers do this once, up front, and then :func:`submodule_update`
    has nothing shared left to write and runs entirely in parallel.
    """
    paths = [str(path) for path in paths]
    if paths:
        run_in_superproject(["git", "submodule", "init", "--", *paths])


def submodule_update(
    path: str | PathLike, submodule: SubmoduleInfo | None = None
) -> None:
    """Bring a submodule's working tree to the commit the superproject records.

    Everything here writes that one submodule's own files, so any number of
    submodules can be done at once. It expects the submodule to be registered
    already: call :func:`register_submodules` for the whole set first, which is
    where the shared metadata gets written.

    :param submodule: the ``.gitmodules`` entry for ``path``, read back from
        the file when not given. A caller iterating over the submodules already
        has it, and passing it spares a re-parse per submodule.
    """
    args = []
    # Use git-autoshare if available
    if submodule is None:
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
                prefetch_autoshare(submodule.url)
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
    root = root_path()
    run(["git", "submodule", "update", *args, "--", str(path)], cwd=root, check=True)
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
        pinned_sha = get_pinned_sha(submodule.path, cwd=root)
        if pinned_sha:
            pin_submodule_commit(build_path(submodule.path), pinned_sha)


def submodule_set_url(repo_path, url, remote="origin"):
    run_in_superproject(
        ["git", "config", "--file=.gitmodules", f"submodule.{repo_path}.url", url]
    )


def set_remote_url(repo_path, url, remote="origin", add=False):
    submodule_set_url(repo_path, url, remote=remote)
    cmd = ["git", "remote", "set-url", remote, url]
    if add:
        cmd = ["git", "remote", "add", remote, url]
    run(cmd, cwd=build_path(repo_path), check=True)


def checkout(branch_name, remote="origin", cwd=None):
    run(["git", "fetch", remote, branch_name], cwd=cwd)
    run(["git", "checkout", f"{remote}/{branch_name}"], cwd=cwd)


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


def get_out_of_sync_submodules() -> set[str]:
    """Return submodules whose checked-out commit differs from HEAD.

    Git's ``submodule status`` uses a leading character to describe the
    relationship between the checked-out submodule commit and the commit
    recorded by the current parent repository:

    * `` `` - checked out at the recorded commit
    * ``+`` - checked out at a different commit
    * ``-`` - submodule is not initialized
    * ``U`` - submodule has merge conflicts

    Uninitialized submodules are considered out of sync because
    ``submodule_update()`` is responsible for initializing them.

    A submodule with merge conflicts is deliberately not considered out of sync:
    ``git submodule update`` should not silently interfere with a conflicted
    working tree.
    """
    output = run(["git", "submodule", "status"], cwd=root_path(), check=True)
    out_of_sync = set()
    for line in output.splitlines():
        if line and line[0] in {"+", "-"} and len(parts := line[1:].split()) > 1:
            out_of_sync.add(parts[1])
    return out_of_sync


def submodule_upgrade(path, url, branch=None):
    """Upgrade a submodule to the tip of the branch it tracks.

    The branch is fetched from ``url`` and exactly what came back is checked
    out. Deliberately not ``git submodule update --remote``, which decides for
    itself where the tip is: it resolves the branch against whichever *local*
    remote happens to match the recorded url, and does not fetch that remote --
    so a remote-tracking ref nobody has refreshed lately upgrades the submodule
    to a commit that old, and says nothing about it. Fetching by url and
    checking out ``FETCH_HEAD`` leaves nothing to guess.

    :param path: submodule path (relative to project root)
    :param url: submodule remote url, as recorded in ``.gitmodules``
    :param branch: the branch to move to; the submodule's own by default
    :returns: True if the submodule was upgraded, False otherwise
    """
    commit_before = get_submodule_commit(path)
    abs_path = str(build_path(path))
    if not branch:
        submodule = next(iter_gitmodules(filter_path=path), None)
        branch = (submodule.branch if submodule else None) or get_odoo_version()
    # As `git submodule update --force` did: a submodule is not somewhere to
    # keep work, and the checkout below would refuse to move over it.
    run(["git", "-C", abs_path, "reset", "--hard", "HEAD"], check=True)
    run(["git", "-C", abs_path, "fetch", url, branch], check=True)
    run(["git", "-C", abs_path, "checkout", "--detach", "FETCH_HEAD"], check=True)
    commit_after = get_submodule_commit(path)
    if commit_before != commit_after:
        ui.echo(f"UPGRADED {path}: {commit_before} -> {commit_after}")
        return True
    else:
        ui.echo(f"NOT UPGRADED {path}: already up to date ({commit_before})")
        return False
