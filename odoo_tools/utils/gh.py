# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import re

from . import ui
from .os_exec import run
from .proj import get_project_manifest_key


def parse_github_url(entity_spec):
    # "entity" is either a PR, commit or a branch
    # TODO: input validation

    # check if it's in a custom pull format // nmspc/repo#pull
    custom_parts = re.match(r"([\w-]+)/([\w-]+)#(\d+)", entity_spec)
    if custom_parts:
        entity_type = "pull"
        upstream, repo_name, entity_id = custom_parts.groups()
    else:
        # this is meant to be an web link then
        # Example:
        # https://github.com/namespace/repo/pull/1234/files#diff-deadbeef
        # parts 0, 1 and 2  /    p3   / p4 / p5 / p6 | part to trim
        #                    ========= ==== ==== ====
        # as we're not interested in parts 7 and beyond, we're just trimming it
        # this is done to allow passing link w/ trailing garbage to this task
        try:
            upstream, repo_name, entity_type, entity_id = entity_spec.split("/")[3:7]
        except ValueError:
            msg = (
                f"Could not parse: {entity_spec}.\n"
                "Accept formats are either:\n"
                "* Full PR URL: https://github.com/user/repo/pull/1234/files#diff-deadbeef\n"
                "* Short PR ref: user/repo#pull-request-id"
                "* Cherry-pick URL: https://github.com/user/repo/[tree]/<commit SHA>"
            )
            raise ValueError(msg) from None

    # force uppercase in OCA upstream name:
    # otherwise `oca` and `OCA` are treated as different namespaces
    if upstream.lower() == "oca":
        upstream = "OCA"

    return {
        "upstream": upstream,
        "repo_name": repo_name,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }


# TODO: add tests
def get_current_rebase_branch():
    current_branch = None
    for rebase_file in ("rebase-merge", "rebase-apply"):
        # in case of rebase, the ref of the branch is in one of these
        # directories, in a file named "head-name"
        path = run(f"git rev-parse --git-path {rebase_file}")
        if os.path.exists(path):
            with open(os.path.join(path, "head-name")) as rf:
                current_branch = rf.read().strip().replace("refs/heads/", "")
            break
    return current_branch


# TODO: add tests


def get_current_branch():
    return run("git symbolic-ref --short HEAD")


# TODO: add tests
# TODO: not sure how much of this is needed w/o submodules
def get_target_branch(target_branch=None):
    """Gets the branch to push on and checks if we're overriding something.

    If target_branch is given only checks for the override.
    Otherwise create the branch name and check for the override.
    """
    current_branch = get_current_rebase_branch()
    if not current_branch:
        current_branch = get_current_branch()
    project_id = get_project_manifest_key("project_id")
    if not target_branch:
        commit = run("git rev-parse HEAD")[:8]
        target_branch = f"merge-branch-{project_id}-{current_branch}-{commit}"
    if current_branch == "master" or re.match(r"\d{1,2}.\d", target_branch):
        ui.ask_or_abort(
            f"You are on branch {current_branch}."
            f" Please confirm override of target branch {target_branch}"
        )
    return target_branch


def check_git_diff(direct_abort=False):
    try:
        run("git diff --quiet --exit-code")
        run("git diff --cached --quiet --exit-code")
    except Exception:
        if direct_abort:
            ui.exit_msg("Your repository has local changes. Abort.")
        # FIXME: should be where it gets called
        ui.ask_or_abort(
            "Your repository has local changes, are you sure you want to continue?"
        )
