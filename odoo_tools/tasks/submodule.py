# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import logging
import re
from itertools import chain
from pathlib import Path

import requests
from git import Repo as GitRepo
from invoke import exceptions, task

from .common import (
    GIT_C2C_REMOTE_NAME,
    MIGRATION_FILE,
    PENDING_MERGES_DIR,
    ask_confirmation,
    ask_or_abort,
    build_path,
    cd,
    cookiecutter_context,
    exit_msg,
    get_migration_file_modules,
    root_path,
    yaml_load,
)
from .module import Module

try:
    import git_aggregator.config
    import git_aggregator.main
    import git_aggregator.repo
except ImportError:
    print("Missing git-aggregator from requirements")
    print("Please run `pip install -r tasks/requirements.txt`")

try:
    import git_autoshare  # noqa: F401
    from git_autoshare.core import find_autoshare_repository

    AUTOSHARE_ENABLED = True
except ImportError:
    print("Missing git-autoshare from requirements")
    print("Please run `pip install -r tasks/requirements.txt`")
    AUTOSHARE_ENABLED = False


try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
except ImportError:
    print("Missing ruamel.yaml from requirements")
    print("Please run `pip install -r tasks/requirements.txt`")


try:
    input = raw_input
except NameError:
    pass

BRANCH_EXCLUDE = """
branches:
  except:
    - /^merge-branch-.*$/
"""
yaml = YAML()

git_aggregator.main.setup_logger()


class Repo:
    """Handle repository/submodule homogeneously."""

    def __init__(self, name_or_path, path_check=True):
        self.path = self.build_submodule_path(name_or_path)
        self.abs_path = build_path(self.path)
        # ensure that given submodule is a mature submodule
        self.abs_merges_path = self.build_submodule_merges_path(self.path)
        self.merges_path = self.build_submodule_merges_path(self.path, relative=True)
        if path_check:
            self._check_paths()
        self.name = self._safe_module_name(name_or_path)

    def _check_paths(self):
        if not (self.path / ".git").exists():
            exit_msg(
                "GIT CONFIG NOT FOUND. "
                f"{self.path} does not look like a mature repository. "
                "Aborting."
            )
        if not self.abs_merges_path.exists():
            exit_msg(f"NOT FOUND `{self.abs_merges_path}'.")

    @classmethod
    def _safe_module_name(cls, name_or_path):
        return name_or_path.rstrip("/").rsplit("/", 1)[-1]

    @classmethod
    def build_submodule_path(cls, name_or_path):
        """Return a submodule path by a submodule name."""
        submodule_name = cls._safe_module_name(name_or_path)
        is_src = submodule_name in ("odoo", "ocb", "src")
        if is_src:
            relative_path = Path("odoo/src")
        else:
            relative_path = Path(f"odoo/external-src/{submodule_name}")
        return relative_path

    @classmethod
    def build_submodule_merges_path(cls, name_or_path, relative=False):
        """Return a pending-merges file for a given submodule.

        :param submodule: either a full path or a bare submodule name,
        as it is known at Github (i.e., `odoo` would stand for `odoo/src`)
        """
        submodule_name = cls._safe_module_name(name_or_path)
        if submodule_name.lower() in ("odoo", "ocb"):
            submodule_name = "src"
        base_path = Path(PENDING_MERGES_DIR)
        if relative:
            base_path = base_path.relative_to(base_path.parent)
        return base_path / f"{submodule_name}.yml"

    def aggregator_config(self):
        return git_aggregator.config.load_config(self.abs_merges_path)[0]

    def get_aggregator(self, **extra_config):
        repo_config = self.aggregator_config()
        repo_config.update(extra_config)
        repo = git_aggregator.repo.Repo(**repo_config)
        repo.cwd = self.abs_path
        return repo

    @classmethod
    def repositories_from_pending_folder(cls, path=None):
        path = Path(path or PENDING_MERGES_DIR)
        return [cls(yml_file.stem) for yml_file in path.glob("*.yml")]

    def has_pending_merges(self):
        if not self.abs_merges_path.exists():
            return False
        # either empty or commented out
        return bool(self.merges_config())

    def merges_config(self):
        data = yaml_load(self.abs_merges_path.read_text()) or {}
        submodule_relpath = ".." / self.path
        return data.get(submodule_relpath, {})

    def update_merges_config(self, config):
        # get former config if any
        if self.abs_merges_path.exists():
            data = yaml_load(self.abs_merges_path.read_text())
        else:
            data = {}
        submodule_relpath = ".." / self.path
        data[submodule_relpath] = config
        with self.abs_merges_path.open("w") as fobj:
            yaml.dump(data, fobj)

    def api_url(self):
        return f"https://api.github.com/repos/{GIT_C2C_REMOTE_NAME}/{self.name}"

    def ssh_url(self, namespace):
        return self.build_ssh_url(namespace, self.name)

    @classmethod
    def build_ssh_url(cls, namespace, repo_name):
        return f"git@github.com:{namespace}/{repo_name}"


def get_target_branch(ctx, target_branch=None):
    """Gets the branch to push on and checks if we're overriding something.

    If target_branch is given only checks for the override.
    Otherwise create the branch name and check for the override.
    """
    for rebase_file in ("rebase-merge", "rebase-apply"):
        # in case of rebase, the ref of the branch is in one of these
        # directories, in a file named "head-name"
        cmd = f"git rev-parse --git-path {rebase_file}"
        path = Path(ctx.run(cmd, hide=True).stdout.strip())
        if path.is_dir():
            hname = (path / "head-name").read_text().strip()
            current_branch = hname.replace("refs/heads/", "")
            break
    else:
        cmd = "git symbolic-ref --short HEAD"
        current_branch = ctx.run(cmd, hide=True).stdout.strip()
    project_id = cookiecutter_context()["project_id"]
    if not target_branch:
        commit = ctx.run("git rev-parse HEAD", hide=True).stdout.strip()[:8]
        target_branch = f"merge-branch-{project_id}-{current_branch}-{commit}"
    if current_branch == "master" or re.match(r"\d{1,2}.\d", target_branch):
        ask_or_abort(
            f"You are on branch {current_branch}."
            f" Please confirm override of target branch {target_branch}"
        )
    return target_branch


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
        rf"git config -f {gitmodules} --get-regexp '^submodule\..*\.path$'",
        hide=True,
    )
    odoo_version = cookiecutter_context()["odoo_version"]
    with cd(root_path()):
        for line in res.stdout.splitlines():
            path_key, path = line.split()
            url_key = path_key.replace(".path", ".url")
            url = ctx.run(
                f'git config -f {gitmodules} --get "{url_key}"',
                hide=True,
            ).stdout
            try:
                ctx.run(f"{add_command} -b {odoo_version} {url.strip()} {path.strip()}")
            except exceptions.Failure:
                pass

    print("Submodules added")
    print()
    print("You can now update odoo/Dockerfile with this addons-path:")
    print()
    ls(ctx)


@task(name="list")
def deprecated_list(ctx, dockerfile=True):
    print(
        "##############################################################\n"
        "submodule.list is deprecated, please use submodule.ls instead\n"
        "##############################################################\n"
    )
    ls(ctx, dockerfile=dockerfile)


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
        f"git config --file {gitmodules} --get-regexp path | awk '{{ print $2 }}' ",
        hide=True,
    )
    content = res.stdout
    if dockerfile:
        blacklist = {"odoo/src"}
        lines = (line for line in content.splitlines() if line not in blacklist)
        lines = chain(lines, ["odoo/src/addons", "odoo/local-src"])
        addons_path = ", \\\n".join(f"/{line}" for line in lines)
        print(f'ENV ADDONS_PATH="{addons_path}" \\\n')
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

    repo = Repo(submodule_path)

    target_branch = get_target_branch(ctx, target_branch=target_branch)
    print(f"Building and pushing to camptocamp/{target_branch}")
    print()
    aggregator = _aggregate(repo, target_branch=target_branch)
    process_travis_file(ctx, repo)
    if push:
        aggregator.push()


def _aggregate(repo, target_branch=None):
    aggregator = repo.get_aggregator(
        target={"branch": target_branch, "remote": GIT_C2C_REMOTE_NAME}
    )
    aggregator.aggregate()
    return aggregator


@task
def push(ctx, submodule_path, target_branch=None):
    """Push a Submodule

    Pushes the current state of your submodule to the target remote and branch
    either given by you or specified in pending-merges.yml
    """
    repo = Repo(submodule_path)
    target_branch = get_target_branch(ctx, target_branch=target_branch)
    print(f"Pushing to camptocamp/{target_branch}")
    print()
    aggregator = repo.get_aggregator(
        target={"branch": target_branch, "remote": GIT_C2C_REMOTE_NAME}
    )
    with cd(repo.path):
        aggregator._switch_to_branch(target_branch)
        process_travis_file(ctx, repo)
        aggregator.push()


def process_travis_file(ctx, repo):
    tf = repo.abs_path / ".travis.yml"
    if not tf.exists():
        print(f"{tf} does not exist. Skipping travis exclude commit")
        return

    print(f"Writing exclude branch option in {tf.name}")
    with tf.open("a") as travis:
        travis.write(BRANCH_EXCLUDE)

    cmd = f'git commit {tf.name} --no-verify -m "Travis: exclude new branch from build"'

    with cd(repo.abs_path):
        commit = ctx.run(cmd, hide=True)
    print(f"Committed as:\n{commit.stdout.strip()}")


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
        repositories = Repo.repositories_from_pending_folder()
    else:
        repositories = [Repo(submodule_path)]
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
                    f"  {str(i).zfill(2)})",
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
    if any([purge_closed, purge_merged]):
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
            ar_dir = Path(ar.repo_dir)
            if not ar_dir.exists():
                ar.prefetch(True)
            update_cmd += f" --reference {ar_dir}"
    update_cmd = f"{update_cmd} {path}"
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
        f"git config --file {gitmodules} --get-regexp 'path' | awk '{{ print $2 }}' ",
        hide=True,
    )
    urls = ctx.run(
        f"git config --file {gitmodules} --get-regexp 'url' | awk '{{ print $2 }}' ",
        hide=True,
    )

    module_list = zip(paths.stdout.splitlines(), urls.stdout.splitlines())

    if submodule_path is not None:
        submodule_path = Path(submodule_path).resolve()
        sync_cmd += f" -- {submodule_path}"
        module_list = [
            (path, url)
            for path, url in module_list
            if Path(path).resolve() == submodule_path
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
    repo = repo or Repo(submodule_path)

    if repo.has_pending_merges():
        # read everything we can reach
        # for reading purposes only
        data = yaml_load(repo.abs_merges_path.read_text())
        submodule_pending_config = data[str(Path("..") / repo.path)]
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
    elif repo.path == Path("odoo/src"):
        # special way to treat that particular submodule
        if ask_confirmation("Use odoo:odoo instead of OCA/OCB?"):
            new_remote_url = Repo.build_ssh_url("odoo", "odoo")
        else:
            new_remote_url = Repo.build_ssh_url("OCA", "OCB")
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
            new_repo = input(f"Repo name [{default_repo}]: ") or default_repo
            new_remote_url = Repo.build_ssh_url(new_namespace, new_repo)

    ctx.run(f"git config --file=.gitmodules submodule.{repo.path}.url {new_remote_url}")
    relative_name = str(repo.path).replace("../", "")
    with cd(repo.abs_path):
        ctx.run(f"git remote set-url origin {new_remote_url}")

    print(f"Submodule {repo.path} is now being sourced from {new_remote_url}")

    if repo.has_pending_merges():
        # we're being polite here, excode 1 doesn't apply to this answer
        ask_or_abort(f"Rebuild consolidation branch for {relative_name}?")
        push = ask_confirmation(f"Push it to `{GIT_C2C_REMOTE_NAME}'?")
        merges(ctx, relative_name, push=push)
    else:
        odoo_version = cookiecutter_context()["odoo_version"]
        if ask_confirmation(
            f"Submodule {relative_name} has no pending merges. Update it to {odoo_version}?"
        ):
            with cd(repo.abs_path):
                ctx.run(f"git fetch origin {odoo_version}")
                ctx.run(f"git checkout origin/{odoo_version}")


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
            exit_msg(msg)

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


def generate_pending_merges_file_template(repo, upstream):
    """Create a submodule merges file from template.

    That should be either `odoo/src` or `odoo/external-src/<module>`
    """
    # could be that this is the first PM ever added to this project
    PENDING_MERGES_DIR.mkdir(parents=True, exists_ok=True)

    oca_ocb_remote = False
    if repo.path == Path("odoo/src") and upstream == "odoo":
        oca_ocb_remote = not ask_confirmation("Use odoo:odoo instead of OCA/OCB?")

    remote_upstream_url = repo.ssh_url(upstream)
    remote_c2c_url = repo.ssh_url(GIT_C2C_REMOTE_NAME)
    cc_context = cookiecutter_context()
    odoo_version = cc_context["odoo_version"]
    default_target = f"merge-branch-{cc_context['project_id']}-master"
    remotes = CommentedMap()
    remotes.insert(0, upstream, remote_upstream_url)

    if oca_ocb_remote:
        # use the oca remote as base even if we are adding an
        # odoo/odoo#123 pull request
        remotes.insert(0, "oca", Repo.build_ssh_url("OCA", "OCB"))

    if upstream != GIT_C2C_REMOTE_NAME:
        # if origin is not the same: add c2c one
        remotes.insert(0, GIT_C2C_REMOTE_NAME, remote_c2c_url)
    config = CommentedMap()
    config.insert(0, "remotes", remotes)
    config.insert(1, "target", f"{GIT_C2C_REMOTE_NAME} {default_target}")
    if oca_ocb_remote:
        base_merge = "{} {}".format("oca", odoo_version)
    else:
        base_merge = f"{upstream} {odoo_version}"
    config.insert(2, "merges", CommentedSeq([base_merge]))
    repo.update_merges_config(config)


def add_pending_pull_request(repo, conf, upstream, pull_id):
    odoo_version = cookiecutter_context().get("odoo_version")
    pending_mrg_line = f"{upstream} refs/pull/{pull_id}/head"
    if pending_mrg_line in conf.get("merges", {}):
        exit_msg(
            f"Requested pending merge is already mentioned in {repo.abs_merges_path} "
        )

    response = requests.get(f"{repo.api_url()}/pulls/{pull_id}")

    # TODO: auth
    base_branch = response.json().get("base", {}).get("ref")
    if response.ok:
        if base_branch:
            if base_branch != odoo_version:
                ask_or_abort(
                    "Requested PR targets branch different from"
                    " current project's major version. Proceed?"
                )
    else:
        print(
            f"Github API call failed ({response.status_code}):"
            " skipping target branch validation."
        )

    # TODO: handle comment
    # if response.ok:
    #     # probably, wrapping `if` could be an overkill
    #     pending_mrg_comment = response.json().get('title')
    # else:
    #     pending_mrg_comment = False
    #     print('Unable to get a pull request title.'
    #           ' You can provide it manually by editing {}.'.format(
    #               repo.abs_merges_path))

    known_remotes = conf["remotes"]
    if upstream not in known_remotes:
        known_remotes.insert(0, upstream, repo.ssh_url(upstream))
    # we're just at the place to append a new pending merge
    # ruamel.yaml's API won't allow ppl to insert items at the end of
    # array, so the closest solution would be to insert it at position 1,
    # straight after `OCA basebranch` merge item.
    conf["merges"].insert(1, pending_mrg_line)


def add_pending_commit(repo, conf, upstream, commit_sha):
    # TODO search in local git history for full hash
    if len(commit_sha) < 40:
        ask_or_abort(
            "You are about to add a patch referenced by a short commit SHA.\n"
            "It's recommended to use fully qualified 40-digit hashes though.\n"
            "Continue?"
        )
    fetch_commit_line = f"git fetch {upstream} {commit_sha}"
    pending_mrg_line = f'git am "$(git format-patch -1 {commit_sha} -o ../patches)"'

    if pending_mrg_line in conf.get("shell_command_after", {}):
        exit_msg(
            f"Requested pending merge is mentioned in {repo.abs_merges_path} already"
        )
    if "shell_command_after" not in conf:
        conf["shell_command_after"] = CommentedSeq()

    # TODO propose a default comment format
    comment = input("Comment? (would appear just above new pending merge, optional):\n")
    conf["shell_command_after"].extend([fetch_commit_line, pending_mrg_line])
    # Add a comment in the list of shell commands
    pos = conf["shell_command_after"].index(fetch_commit_line)
    conf["shell_command_after"].yaml_set_comment_before_after_key(
        pos, before=comment, indent=2
    )
    print(f"📋 cherry pick {upstream}/{commit_sha} has been added")


@task
def add_pending(ctx, entity_url):
    """Add a pending merge using given entity link"""
    # pattern, given an https://github.com/<user>/<repo>/pull/<pr-index>
    # # PR headline
    # # PR link as is
    # - refs/pull/<pr-index>/head
    parts = parse_github_url(entity_url)

    upstream = parts.get("upstream")
    repo_name = parts.get("repo_name")
    entity_type = parts.get("entity_type")
    entity_id = parts.get("entity_id")

    repo = Repo(repo_name, path_check=False)
    if not repo.abs_merges_path.exists():
        generate_pending_merges_file_template(repo, upstream)

    conf = repo.merges_config()
    if entity_type == "pull":
        add_pending_pull_request(repo, conf, upstream, entity_id)
    elif entity_type in ("commit", "tree"):
        add_pending_commit(repo, conf, upstream, entity_id)

    # write back a file
    repo.update_merges_config(conf)
    sync_remote(ctx, repo=repo)


def remove_pending_commit(repo, conf, upstream, commit_sha):
    lines_to_drop = [
        f"git fetch {upstream} {commit_sha}",
        f'git am "$(git format-patch -1 {commit_sha} -o ../patches)"',
    ]
    if lines_to_drop[0] not in conf.get("shell_command_after", {}) and lines_to_drop[
        1
    ] not in conf.get("shell_command_after", {}):
        exit_msg(
            f"No such reference found in {repo.abs_merges_path},"
            " having troubles removing that:\n"
            f"Looking for:\n- {lines_to_drop[0]}\n- {lines_to_drop[1]}"
        )
    for line in lines_to_drop:
        if line in conf:
            conf["shell_command_after"].remove(line)
    if not conf["shell_command_after"]:
        del conf["shell_command_after"]
    print(f"✨ cherry pick {upstream}/{commit_sha} has been removed")


def remove_pending_pull(repo, conf, upstream, pull_id):
    line_to_drop = f"{upstream} refs/pull/{pull_id}/head"
    if line_to_drop not in conf["merges"]:
        exit_msg(
            f"No such reference found in {repo.abs_merges_path},"
            " having troubles removing that:\n"
            f"Looking for: {line_to_drop}"
        )
    conf["merges"].remove(line_to_drop)


@task
def remove_pending(ctx, entity_url):
    """Remove a pending merge using given entity link"""

    parts = parse_github_url(entity_url)

    upstream = parts.get("upstream")
    repo_name = parts.get("repo_name")
    repo = Repo(repo_name)
    entity_type = parts.get("entity_type")
    entity_id = parts.get("entity_id")

    config = repo.merges_config()
    if entity_type == "pull":
        remove_pending_pull(repo, config, upstream, entity_id)
    elif entity_type in ("tree", "commit"):
        remove_pending_commit(repo, config, upstream, entity_id)

    # check if that file is useless since it has an empty `merges` section
    # if it does - drop it instead of writing a new file version
    # only the upstream branch is present in `merges`
    # first item is `- oca 11.0` or similar
    pending_merges_present = len(config["merges"]) > 1
    patches = len(config.get("shell_command_after", {}))

    if not pending_merges_present and not patches:
        repo.abs_merges_path.unlink()
        sync_remote(ctx, repo=repo)
    else:
        repo.update_merges_config(config)


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
    migration_modules = get_migration_file_modules(MIGRATION_FILE)
    print(f"\nInstalled modules from {submodule_path}:\n")
    modules = []
    for mod in Path(submodule_path).iter():
        if mod.name in migration_modules:
            modules.append(mod.name)
            print(f"\t- {mod.name}")

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
    submodule_names = sorted(submodules)
    # Display dependencies
    for sub in submodule_names:
        deps = submodules[sub]
        print(f"\n{sub} :")
        for mod in deps:
            print(f"\t- {mod}")


def _get_current_commit_from_submodule(ctx, path):
    """Returns the current in stage commit for a submodule path"""
    ref_cmd = f"git submodule status | grep '{path}' | awk '{{ print $1 }}'"
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
            reference_url = Path(ar.repo_dir)
            if not reference_url.exists():
                ar.prefetch(True)

    if branch:
        with cd(build_path(path)):
            checkout_cmd = (
                "git reset HEAD --hard && "
                f"git fetch {url} && "
                f"git checkout {branch}"
            )
            print(checkout_cmd)
            ctx.run(checkout_cmd)
    else:
        upgrade_cmd = (
            "git submodule update -f --remote "
            f"--checkout --reference {reference_url} {path}"
        )
        print(upgrade_cmd)
        ctx.run(upgrade_cmd)

    upgraded_ref = _get_current_commit_from_submodule(ctx, path)
    if current_ref != upgraded_ref:
        print(f"-- UPGRADED from '{current_ref}' to '{upgraded_ref}'")
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
    odoo_version = cookiecutter_context().get("odoo_version")
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
            sub_repo = Repo(submodule.path, path_check=False)
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
                        f"Replace by odoo version '{odoo_version}'?"
                    ):
                        branch = odoo_version

                # Update to avoid further issues if in bad state
                update(ctx, sub_repo.path)
                # Try to effectively upgrade the submodule
                _cmd_git_submodule_upgrade(ctx, sub_repo.path, submodule.url, branch)
            except Exception as e:
                # Rollback to previous version
                update(ctx, sub_repo.path)
                print(f"ERROR: occurs during '{submodule.name}' upgrade : {e}")
    if unmerged_prs:
        print("\nCAREFULL /!\\")
        print("The following closed PR's could NOT be processed automatically,")
        print("you have to manually manage them :")
        for unmerged_pr in unmerged_prs:
            print(f"- {unmerged_pr}")
    return unmerged_prs
