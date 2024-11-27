# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import subprocess

try:
    import git_autoshare  # noqa: F401
    from git_autoshare.core import find_autoshare_repository  # noqa: F401

    AUTOSHARE_ENABLED = True
except ImportError:
    print("Missing git-autoshare from requirements")
    print("Please run `pip install -r tasks/requirements.txt`")
    AUTOSHARE_ENABLED = False


from . import ui
from .path import build_path
from .proj import get_current_version


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


def iter_submodules():
    """yields the submodules from `.gitmodule`"""
    output = subprocess.run(
        [
            "git",
            "config",
            "-f",
            _get_gitmodules(),
            "--get-regexp",
            "^submodule\\..*\\.path$",
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    for line in output.splitlines():
        yield line.strip()


def submodule_add(submodule_line):
    add_command = ["git", "submodule", "add"]
    if AUTOSHARE_ENABLED:
        add_command = ["git", "autoshare-submodule-add"]
    odoo_serie = get_current_version(serie_only=True)
    branch = f"{odoo_serie}.0"
    path_key, path = submodule_line.split()
    url_key = path_key.replace(".path", ".url")
    url = subprocess.run(
        ["git", "config", "-f", _get_gitmodules(), "--get", url_key],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    try:
        res = subprocess.run(
            add_command + ["-b", branch, url, path],
        )
        print(res.returncode)
    except:
        raise


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
