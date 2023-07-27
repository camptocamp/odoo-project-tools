# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import logging
import os
from itertools import chain

import requests
from git import Repo as GitRepo
from invoke import exceptions, task

from ..config import get_conf_key
from ..utils import pending_merge as pm_utils
from ..utils.gh import get_target_branch
from ..utils.marabunta import MarabuntaFileHandler
from ..utils.os_exec import run
from ..utils.path import build_path, cd, root_path
from ..utils.proj import get_project_manifest_key
from ..utils.ui import ask_confirmation, ask_or_abort, exit_msg
from ..utils.yaml import yaml_load
from .module import Module

try:
    import git_autoshare  # noqa: F401
    from git_autoshare.core import find_autoshare_repository

    AUTOSHARE_ENABLED = True
except ImportError:
    print("Missing git-autoshare")
    AUTOSHARE_ENABLED = False


try:
    input = raw_input
except NameError:
    pass

BRANCH_EXCLUDE = """
branches:
  except:
    - /^merge-branch-.*$/
"""


GIT_C2C_REMOTE_NAME = get_conf_key("company_git_remote")


@task
def init(ctx):
    """Add git submodules read in the .gitmodules files.

    Allow to edit the .gitmodules file, add all the repositories and
    run the command once to add all the submodules.

    It means less 'git submodule add -b ... {url} {path}' commands to run

    """
    add_command = "git submodule add"
    if AUTOSHARE_ENABLED:
        add_command = "git autoshare-submodule-add"
    gitmodules = build_path(".gitmodules")
    res = ctx.run(
        r"git config -f %s --get-regexp '^submodule\..*\.path$'" % gitmodules,
        hide=True,
    )
    odoo_version = get_project_manifest_key("odoo_version")
    with cd(root_path()):
        for line in res.stdout.splitlines():
            path_key, path = line.split()
            url_key = path_key.replace(".path", ".url")
            url = ctx.run(
                'git config -f {} --get "{}"'.format(gitmodules, url_key),
                hide=True,
            ).stdout
            try:
                ctx.run(
                    "%s -b %s %s %s"
                    % (add_command, odoo_version, url.strip(), path.strip())
                )
            except exceptions.Failure:
                pass

    print("Submodules added")
    print()
    print("You can now update odoo/Dockerfile with this addons-path:")
    print()
    ls(ctx)


@task(
    help={
        "dockerfile": "With --no-dockerfile, the raw paths are listed instead "
        "of the Dockerfile format"
    }
)
def ls(ctx, dockerfile=True):
    """List git submodules paths.

    It can be used to directly copy-paste the addons paths in the Dockerfile.
    The order depends of the order in the .gitmodules file.

    """
    gitmodules = build_path(".gitmodules")
    res = ctx.run(
        "git config --file %s --get-regexp path | awk '{ print $2 }' " % gitmodules,
        hide=True,
    )
    content = res.stdout
    # TODO: change depending on new structure
    # use root_path to get root project directory
    if dockerfile:
        blacklist = {"odoo/src"}
        lines = (line for line in content.splitlines() if line not in blacklist)
        lines = chain(lines, ["odoo/src/addons", "odoo/local-src"])
        lines = ("/%s" % line for line in lines)
        template = 'ENV ADDONS_PATH="%s" \\\n'
        print(template % (", \\\n".join(lines)))
    else:
        print(content)


@task
def merges(ctx, submodule_path, push=True, target_branch=None):
    """Regenerate a pending branch for a submodule.

    Use case: a PR has been updated and you want to refresh it.

    It reads pending-merges.d/sub-name.yml, runs gitaggregator on the submodule
    and pushes the new branch on dynamic target constructed as follows:
    camptocamp/merge-branch-<project_id>-<branch>-<commit>

    By default, the branch is pushed on the camptocamp remote, but you
    can disable the push with ``--no-push``.

    Beware, if you changed the remote of the submodule manually, you still need
    to run `sync_remote` manually.
    """

    repo = pm_utils.Repo(submodule_path)
    target_branch = get_target_branch(target_branch=target_branch)
    print("Building and pushing to camptocamp/{}".format(target_branch))
    print()
    aggregator = repo.get_aggregator(target_branch=target_branch)
    process_travis_file(repo)
    if push:
        aggregator.push()


@task
def push(ctx, submodule_path, target_branch=None):
    """Push a Submodule

    Pushes the current state of your submodule to the target remote and branch
    either given by you or specified in pending-merges.yml
    """
    repo = pm_utils.Repo(submodule_path)
    target_branch = get_target_branch(target_branch=target_branch)
    print("Pushing to camptocamp/{}".format(target_branch))
    print()
    aggregator = repo.get_aggregator(target_branch=target_branch)
    with cd(repo.path):
        aggregator._switch_to_branch(target_branch)
        process_travis_file(repo)
        aggregator.push()


# FIXME: must check if the repo uses travis or GH actions
# TODO: add GH actions exclude support
def process_travis_file(repo):
    tf = ".travis.yml"
    with cd(repo.abs_path):
        if not os.path.exists(tf):
            print(
                repo.abs_path + tf,
                "does not exists. Skipping travis exclude commit",
            )
            return

        print("Writing exclude branch option in {}".format(tf))
        with open(tf, "a") as travis:
            travis.write(BRANCH_EXCLUDE)

        cmd = 'git commit {} --no-verify -m "Travis: exclude new branch from build"'
        commit = run(cmd.format(tf), hide=True)
        print("Committed as:\n{}".format(commit.stdout.strip()))


@task
def show_prs(ctx, submodule_path=None, state=None, purge=None):
    """Show all pull requests in pending merges.

    Pass nothing to check all submodules.
    Pass `-s path/to/submodule` to check specific ones.
    """
    if purge:
        assert purge in ("closed", "merged")
    logging.getLogger("requests").setLevel(logging.ERROR)
    if submodule_path is None:
        repositories = pm_utils.Repo.repositories_from_pending_folder()
    else:
        repositories = [pm_utils.Repo(submodule_path)]
    if not repositories:
        exit_msg("No repo to check.")

    # NOTE: to collect all this info you must provide your GITHUB_TOKEN.
    # See git-aggregator README.
    pr_info_msg = (
        "#{number} {title}\n"
        "      State: {state} ({merged})\n"
        "      Updated at: {updated_at}\n"
        "      View: {html_url}\n"
        "      Shortcut: {shortcut}\n"
    )
    all_repos_prs = {}
    for repo in repositories:
        aggregator = repo.get_aggregator()
        print("--")
        print("Checking:", repo.name)
        print("Path:", repo.path)
        print("Merge file:", repo.merges_path)
        all_prs = aggregator.collect_prs_info()
        if state is not None:
            # filter only our state
            all_prs = {k: v for k, v in all_prs.items() if k == state}
        for pr_state, prs in all_prs.items():
            print("State:", pr_state)
            for i, pr_info in enumerate(prs, 1):
                if "raw" not in pr_info:
                    exit_msg("Upgrade git-aggregator to 1.7.2 or later")
                all_repos_prs.setdefault(pr_state, []).append(pr_info)
                pr_info["raw"].update(pr_info)
                print(
                    "  {})".format(str(i).zfill(2)),
                    pr_info_msg.format(**pr_info["raw"]),
                )
    if purge and all_repos_prs.get("closed", []):
        kw = {f"purge_{purge}": True}
        _purge_closed_prs(ctx, all_repos_prs, **kw)
        # TODO: ask for re-aggregate?
    return all_repos_prs


@task
def show_closed_prs(ctx, submodule_path=None, purge_closed=False, purge_merged=False):
    """Show all closed and unmerged pull requests in pending merges.


    Pass nothing to check all submodules.
    Pass `-s path/to/submodule` to check specific ones.
    """
    all_repos_prs = show_prs(ctx, submodule_path=submodule_path, state="closed")
    return _purge_closed_prs(
        ctx,
        all_repos_prs,
        purge_closed=purge_closed,
        purge_merged=purge_merged,
    )


def _purge_closed_prs(ctx, all_repos_prs, purge_merged=False, purge_closed=False):
    assert purge_closed or purge_merged
    closed_prs = all_repos_prs.get("closed", [])
    closed_unmerged_prs = [pr for pr in closed_prs if pr.get("merged") == "not merged"]
    closed_merged_prs = [pr for pr in closed_prs if pr.get("merged") == "merged"]

    # This list will received all closed and unmerged pr's url to return
    # If purge_closed is set to True, removed prs will not be returned
    unmerged_prs_urls = [pr.get("url") for pr in closed_unmerged_prs]

    if closed_unmerged_prs and purge_closed:
        print("Purging closed ones...")
        for closed_pr_info in closed_unmerged_prs:
            try:
                remove_pending(ctx, closed_pr_info["shortcut"])
                unmerged_prs_urls.remove(closed_pr_info.get("url"))
            except exceptions.Failure as e:
                print(
                    "An error occurs during '{}' removal : {}".format(
                        closed_pr_info.get("url"), e
                    )
                )
    if closed_merged_prs and purge_merged:
        print("Purging merged ones...")
        for closed_pr_info in closed_merged_prs:
            remove_pending(ctx, closed_pr_info["shortcut"])
    return unmerged_prs_urls


def _cmd_git_submodule_update(ctx, path, url):
    update_cmd = "git submodule update --init"

    if AUTOSHARE_ENABLED:
        index, ar = find_autoshare_repository([url])
        if ar:
            if not os.path.exists(ar.repo_dir):
                ar.prefetch(True)
            update_cmd += " --reference {}".format(ar.repo_dir)
    update_cmd = update_cmd + " " + path
    print(update_cmd)
    ctx.run(update_cmd)


@task
def update(ctx, submodule_path=None):
    """Initialize or update submodules

    Synchronize submodules and then launch `git submodule update --init`
    for each submodule.

    If `git-autoshare` is configured locally, it will add `--reference` to
    fetch data from local cache.

    :param submodule_path: submodule path for a precise sync & update

    """
    sync_cmd = "git submodule sync"

    gitmodules = build_path(".gitmodules")
    paths = ctx.run(
        "git config --file %s "
        "--get-regexp 'path' | awk '{ print $2 }' " % (gitmodules,),
        hide=True,
    )
    urls = ctx.run(
        "git config --file %s "
        "--get-regexp 'url' | awk '{ print $2 }' " % (gitmodules,),
        hide=True,
    )

    module_list = list(zip(paths.stdout.splitlines(), urls.stdout.splitlines()))

    if submodule_path is not None:
        submodule_path = os.path.normpath(submodule_path)
        sync_cmd += " -- {}".format(submodule_path)
        module_list = [
            (path, url)
            for path, url in module_list
            if os.path.normpath(path) == submodule_path
        ]

    with cd(root_path()):
        ctx.run(sync_cmd)

        for path, url in module_list:
            _cmd_git_submodule_update(ctx, path, url)


@task
def sync_remote(ctx, submodule_path=None, repo=None, force_remote=False):
    """Use to alter remotes between camptocamp and upstream in .gitmodules.

    :param force_remote: explicit remote to add, if omitted, acts this way:

    * sets upstream to `camptocamp` if `merges` section of it's pending-merges
      file is populated

    * tries to guess upstream otherwise - for `odoo/src` path it is usually
      `OCA/OCB` repository, for anything else it would search for a fork in a
      `camptocamp` namespace and then set the upstream to fork's parent

    Mainly used as a post-execution step for add/remove-pending-merge but it's
    possible to call it directly from the command line.
    """
    assert submodule_path or repo
    repo = repo or pm_utils.Repo(submodule_path)
    if repo.has_pending_merges():
        with open(repo.abs_merges_path) as pending_merges:
            # read everything we can reach
            # for reading purposes only
            data = yaml_load(pending_merges.read())
            submodule_pending_config = data[os.path.join(os.path.pardir, repo.path)]
            merges_in_action = submodule_pending_config["merges"]
            registered_remotes = submodule_pending_config["remotes"]

            if force_remote:
                new_remote_url = registered_remotes[force_remote]
            elif merges_in_action:
                new_remote_url = registered_remotes[GIT_C2C_REMOTE_NAME]
            else:
                new_remote_url = next(
                    remote
                    for remote in registered_remotes.values()
                    if remote != GIT_C2C_REMOTE_NAME
                )
    # TODO: change depending on new structure
    # use root_path to get root project directory
    elif repo.path == "odoo/src":
        # special way to treat that particular submodule
        if ask_confirmation("Use odoo:odoo instead of OCA/OCB?"):
            new_remote_url = pm_utils.Repo.build_ssh_url("odoo", "odoo")
        else:
            new_remote_url = pm_utils.Repo.build_ssh_url("OCA", "OCB")
    else:
        # resolve what's the parent repository from which C2C consolidation
        # one was forked
        response = requests.get(repo.api_url())
        if response.ok:
            info = response.json()
            parent = info.get("parent", {})
            if parent:
                # resolve w/ parent repository
                # C2C consolidation was forked from
                new_remote_url = parent.get("ssh_url")
            else:
                # not a forked repo (eg: camptocamp/connector-jira)
                new_remote_url = info.get("ssh_url")
        else:
            print(
                "Couldn't reach Github API to resolve submodule upstream."
                " Please provide it manually."
            )
            default_repo = repo.name.replace("_", "-")
            new_namespace = input("Namespace [OCA]: ") or "OCA"
            new_repo = input("Repo name [{}]: ".format(default_repo)) or default_repo
            new_remote_url = pm_utils.Repo.build_ssh_url(new_namespace, new_repo)

    ctx.run(
        "git config --file=.gitmodules submodule.{}.url {}".format(
            repo.path, new_remote_url
        )
    )
    relative_name = repo.path.replace("../", "")
    with cd(build_path(relative_name)):
        ctx.run("git remote set-url origin {}".format(new_remote_url))

    print("Submodule {} is now being sourced from {}".format(repo.path, new_remote_url))

    if repo.has_pending_merges():
        # we're being polite here, excode 1 doesn't apply to this answer
        ask_or_abort("Rebuild consolidation branch for {}?".format(relative_name))
        push = ask_confirmation("Push it to `{}'?".format(GIT_C2C_REMOTE_NAME))
        merges(ctx, relative_name, push=push)
    else:
        odoo_version = get_project_manifest_key("odoo_version")
        if ask_confirmation(
            "Submodule {} has no pending merges. Update it to {}?".format(
                relative_name, odoo_version
            )
        ):
            with cd(repo.abs_path):
                os.system("git fetch origin {}".format(odoo_version))
                os.system("git checkout origin/{}".format(odoo_version))


@task
def add_pending(ctx, entity_url):
    """Add a pending merge using given entity link"""
    repo = pm_utils.add_pending(entity_url)
    sync_remote(ctx, repo=repo)


@task
def remove_pending(ctx, entity_url):
    """Remove a pending merge using given entity link"""

    repo = pm_utils.remove_pending(entity_url)
    sync_remote(ctx, repo=repo)


def get_dependency_module_list(modules):
    """Get dependency modules from a list of modules
    construct the dependency list from existing modules in addons_path

    """
    todo = modules[:]
    deps = []
    while todo:
        current = todo.pop()
        for d in Module(current).get_dependencies():
            if d not in modules and d not in deps and d not in todo:
                todo.append(d)
                deps.append(d)
    return deps


@task
def list_external_dependencies_installed(ctx, submodule_path):
    """List installed modules of a specific directory.

    Compare the modules in the submodule path against the installed
    module in odoo/migration.yml.

    eg:
      odoo/external-src/account-closing
        ├── account_cutoff_accrual_base
        ├── account_cutoff_base
        ├── account_cutoff_prepaid
        ├── account_invoice_start_end_dates
        └── account_multicurrency_revaluation

      migration.yml contain account_cutoff_base + account_cutoff_prepaid

      so contain account_cutoff_base + account_cutoff_prepaid are returned

    """
    # TODO: change depending on new structure
    # use root_path to get root project directory
    submodule_path = build_path(submodule_path)
    marabunta_file = get_conf_key("marabunta_mig_file_rel_path")
    migration_modules = MarabuntaFileHandler(
        marabunta_file
    ).get_migration_file_modules()
    print("\nInstalled modules from {}:\n".format(submodule_path))
    modules = []
    with cd(submodule_path):
        for mod in os.listdir():
            if mod in migration_modules:
                modules.append(mod)
                print("\t- " + mod)

    # Construct a dependency name list by submodule
    submodules = {}
    deps = get_dependency_module_list(modules)
    for dep in deps:
        sub = Module(dep).dir
        if sub in modules:
            continue
        if sub not in submodules:
            submodules[sub] = []
        submodules[sub].append(dep)

    if not submodules:
        return
    print("\n\nDependencies:")
    submodule_names = submodules.keys()
    submodule_names = sorted(submodule_names)
    # Display dependencies
    for sub in submodule_names:
        deps = submodules[sub]
        print("\n{} :".format(sub))
        for mod in deps:
            print("\t- " + mod)


def _get_current_commit_from_submodule(ctx, path):
    """Returns the current in stage commit for a submodule path"""
    ref_cmd = "git submodule status | grep '%s' | awk '{ print $1 }'" % path
    commit_hash = ctx.run(ref_cmd, hide=True).stdout
    # Clean for last carriage return and + at the beginning if stage has changed
    return commit_hash.strip("\n").strip("+")


def _cmd_git_submodule_upgrade(ctx, path, url, branch=None):
    """Force update of a submodule.

    If a branch is given, the submodule will be reset and checkout
    """
    current_ref = _get_current_commit_from_submodule(ctx, path)
    reference_url = url
    if AUTOSHARE_ENABLED:
        index, ar = find_autoshare_repository([url])
        if ar:
            if not os.path.exists(ar.repo_dir):
                ar.prefetch(True)
            reference_url = ar.repo_dir

    if branch:
        with cd(build_path(path)):
            checkout_cmd = (
                "git reset HEAD --hard &&\
                            git fetch %s &&\
                            git checkout %s"
                % (url, branch)
            )
            print(checkout_cmd)
            ctx.run(checkout_cmd)
    else:
        upgrade_cmd = (
            "git submodule update -f --remote "
            "--checkout --reference {} {}".format(reference_url, path)
        )
        print(upgrade_cmd)
        ctx.run(upgrade_cmd)

    upgraded_ref = _get_current_commit_from_submodule(ctx, path)
    if current_ref != upgraded_ref:
        print("-- UPGRADED from '{}' to '{}'".format(current_ref, upgraded_ref))
    else:
        print("-- NOT UPGRADED")


@task
def upgrade(ctx, submodule_path=None, force_branch=None):
    """Update and upgrade a submodule to it's latest commit.
    Or all submodules if a submodule path is not specified.

    If a module has a pending merges in state `closed` and `not merged`, it will
    not be processed by this method but a list these pull requests is returned.

    Prerequisites:
        A submodule MUST BE BASED on a valid remote branch (An issue will occurs
        if not).
    """
    odoo_version = get_project_manifest_key("odoo_version")
    project_repo = GitRepo(root_path())
    submodules = project_repo.submodules
    unmerged_prs = []

    if submodule_path:
        submodules = [sm for sm in submodules if sm.path == submodule_path]

    with cd(root_path()):
        for submodule in submodules:
            print("--")
            print("-- Upgrading:", submodule.name)
            print("-- Path:", submodule.path)
            print("-- Branch:", submodule.branch_name)
            branch = None
            sub_repo = pm_utils.Repo(submodule.path, path_check=False)
            try:
                # First pass to close pr's
                # But close `merged` PR's only, not `not merged` !
                if sub_repo.has_pending_merges():
                    print("-- Merge file:", sub_repo.merges_path)
                    unmerged_prs.extend(
                        show_closed_prs(ctx, sub_repo.path, purge_merged=True)
                    )

                # Still pending left > merges to update
                if sub_repo.has_pending_merges():
                    merges(ctx, sub_repo.path, push=True)
                    continue

                # No more pending > Upgrade !

                # To avoid issue while upgrading in a branch that does not
                # exists in the remote or is detached, we must confirm that
                # branch named differently that the Odoo version is properly
                # indicated in the gitmodule
                if force_branch:
                    branch = force_branch
                elif submodule.branch_name != odoo_version and not force_branch:
                    if ask_confirmation(
                        "Configured target branch differs from current project"
                        " major version (this can lead to impossible upgrade,"
                        " you should also properly indicate it in the"
                        " gitmodules file). "
                        "Replace by odoo version '%s'?" % odoo_version
                    ):
                        branch = odoo_version

                # Update to avoid further issues if in bad state
                update(ctx, sub_repo.path)
                # Try to effectively upgrade the submodule
                _cmd_git_submodule_upgrade(ctx, sub_repo.path, submodule.url, branch)
            except Exception as e:
                # Rollback to previous version
                update(ctx, sub_repo.path)
                print(
                    "ERROR: occurs during '{}' upgrade : {}".format(submodule.name, e)
                )
    if unmerged_prs:
        print("\nCAREFULL /!\\")
        print("The following closed PR's could NOT be processed automatically,")
        print("you have to manually manage them :")
        for unmerged_pr in unmerged_prs:
            print("- {}".format(unmerged_pr))
    return unmerged_prs
