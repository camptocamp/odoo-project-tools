# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import logging
import os
from pathlib import PosixPath

import git_aggregator.config
import git_aggregator.main
import git_aggregator.repo
import requests
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ..config import get_conf_key
from ..exceptions import PathNotFound
from . import gh, ui
from .os_exec import run
from .path import build_path, cd
from .proj import get_current_version, get_project_manifest_key
from .yaml import yaml_dump, yaml_load

git_aggregator.main.setup_logger()


try:
    input = raw_input
except NameError:
    pass

git_aggregator.main.setup_logger()


class Repo:
    """Handle checked out repositories and their pending merges."""

    def __init__(self, name_or_path, path_check=True):
        self.company_git_remote = get_conf_key("company_git_remote")
        self.odoo_src_rel_path = get_conf_key("odoo_src_rel_path")
        self.ext_src_rel_path = get_conf_key("ext_src_rel_path")
        self.pending_merge_rel_path = get_conf_key("pending_merge_rel_path")
        self.pending_merge_abs_path = build_path(self.pending_merge_rel_path)
        self.path = self.make_repo_path(name_or_path)
        self.abs_path = build_path(self.path)
        # ensure that given submodule is a mature submodule
        self.abs_merges_path = self.make_repo_merges_path(self.path)
        self.merges_path = self.make_repo_merges_path(self.path, relative=True)
        if path_check:
            self._check_paths()
        self.name = self._safe_repo_name(name_or_path)

    def _check_paths(self):
        if not (self.abs_path / ".git").exists():
            raise PathNotFound(
                "GIT CONFIG NOT FOUND. "
                "{} does not look like a mature repository. "
                "Aborting.".format(self.abs_path)
            )
        if not self.abs_merges_path.exists():
            raise PathNotFound(
                "MERGES PATH NOT FOUND `{}'.".format(self.abs_merges_path)
            )

    @staticmethod
    def _safe_repo_name(name_or_path):
        # TODO: try to avoid this not homogeneous handling
        if isinstance(name_or_path, PosixPath):
            name_or_path = name_or_path.as_posix()
        return name_or_path.rstrip("/").rsplit("/", 1)[-1]

    def make_repo_path(self, name_or_path):
        """Return a submodule path by a submodule name."""
        submodule_name = self._safe_repo_name(name_or_path)
        is_src = submodule_name in ("odoo", "ocb", "src")
        if is_src:
            relative_path = self.odoo_src_rel_path
        else:
            relative_path = self.ext_src_rel_path / submodule_name
        return relative_path

    def make_repo_merges_path(self, name_or_path, relative=False):
        """Return a pending-merges file for a given repo.

        :param name_or_path: either a full path or a bare repo name,
        as it is known at Github
        """
        repo_name = self._safe_repo_name(name_or_path)
        if repo_name.lower() in ("odoo", "ocb"):
            # FIXME: not sure this will be the path
            repo_name = "src"
        base_path = self.pending_merge_abs_path
        if relative:
            base_path = self.pending_merge_rel_path
        return (base_path / repo_name).with_suffix(".yml")

    @classmethod
    def repositories_from_pending_folder(cls, path=None):
        pending_merge_abs_path = build_path(get_conf_key("pending_merge_rel_path"))
        path = path or pending_merge_abs_path
        repo_names = []
        for root, dirs, files in os.walk(path):
            repo_names = [
                os.path.splitext(fname)[0] for fname in files if fname.endswith(".yml")
            ]
        return [cls(name) for name in repo_names]

    def has_pending_merges(self):
        found = os.path.exists(self.abs_merges_path)
        if not found:
            return False
        # either empty or commented out
        return bool(self.merges_config())

    def merges_config(self):
        with open(self.abs_merges_path) as f:
            data = yaml_load(f.read()) or {}
            # FIXME: this should be relative
            # to the position of the pending merge folder
            repo_relpath = ".." / self.path
            return data.get(repo_relpath.as_posix(), {})

    def update_merges_config(self, config):
        # get former config if any
        if os.path.exists(self.abs_merges_path):
            with open(self.abs_merges_path) as f:
                data = yaml_load(f.read())
        else:
            data = {}
        repo_relpath = os.path.join(os.path.pardir, self.path)
        data[repo_relpath] = config
        with open(self.abs_merges_path, "w") as f:
            yaml_dump(data, f)

    def api_url(self, upstream=None):
        return "https://api.github.com/repos/{}/{}".format(
            upstream or self.company_git_remote, self.name
        )

    def ssh_url(self, namespace=None):
        namespace = namespace or self.company_git_remote
        return self.build_ssh_url(namespace, self.name)

    @classmethod
    def build_ssh_url(cls, namespace, repo_name):
        return "git@github.com:{}/{}.git".format(namespace, repo_name)

    def generate_pending_merges_file_template(self, upstream):
        """Create git-aggregator config for current repo"""
        # could be that this is the first PM ever added to this project
        if not os.path.exists(self.pending_merge_abs_path):
            os.makedirs(self.pending_merge_abs_path)

        oca_ocb_remote = False
        if self.path == self.odoo_src_rel_path and upstream == "odoo":
            oca_ocb_remote = not ui.ask_confirmation(
                "Use odoo:odoo instead of OCA/OCB?"
            )

        remote_upstream_url = self.ssh_url(upstream)
        remote_company_url = self.ssh_url()
        odoo_version = get_project_manifest_key("odoo_version")
        default_target = "merge-branch-{}-master".format(
            get_project_manifest_key("project_id")
        )
        remotes = CommentedMap()
        remotes.insert(0, upstream, remote_upstream_url)

        if oca_ocb_remote:
            # use the oca remote as base even if we are adding an
            # odoo/odoo#123 pull request
            remotes.insert(0, "oca", self.build_ssh_url("OCA", "OCB"))

        if upstream != self.company_git_remote:
            # if origin is not the same: add company's one
            remotes.insert(0, self.company_git_remote, remote_company_url)
        config = CommentedMap()
        config.insert(0, "remotes", remotes)
        config.insert(
            1, "target", "{} {}".format(self.company_git_remote, default_target)
        )
        if oca_ocb_remote:
            base_merge = "{} {}".format("oca", odoo_version)
        else:
            base_merge = "{} {}".format(upstream, odoo_version)
        config.insert(2, "merges", CommentedSeq([base_merge]))
        self.update_merges_config(config)

    def add_pending_pull_request(self, upstream, pull_id):
        conf = self.merges_config()
        odoo_version = get_project_manifest_key("odoo_version")
        pending_mrg_line = "{} refs/pull/{}/head".format(upstream, pull_id)
        if pending_mrg_line in conf.get("merges", {}):
            ui.echo(
                "Requested pending merge is already mentioned in {} ".format(
                    self.abs_merges_path
                )
            )
            return True

        response = requests.get(
            "{}/pulls/{}".format(self.api_url(upstream=upstream), pull_id)
        )

        # TODO: auth
        base_branch = response.json().get("base", {}).get("ref")
        if response.ok:
            if base_branch:
                if base_branch != odoo_version:
                    ui.ask_or_abort(
                        "Requested PR targets branch different from"
                        " current project's major version. Proceed?"
                    )
        else:
            ui.echo(
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
        #               self.abs_merges_path))

        known_remotes = conf["remotes"]
        if upstream not in known_remotes:
            known_remotes.insert(0, upstream, self.ssh_url(upstream))
        # we're just at the place to append a new pending merge
        # ruamel.yaml's API won't allow ppl to insert items at the end of
        # array, so the closest solution would be to insert it at position 1,
        # straight after `OCA basebranch` merge item.
        conf["merges"].insert(1, pending_mrg_line)
        self.update_merges_config(conf)
        return True

    def add_pending_commit(self, upstream, commit_sha, skip_questions=True):
        conf = self.merges_config()
        # TODO search in local git history for full hash
        if len(commit_sha) < 40:
            ui.ask_or_abort(
                "You are about to add a patch referenced by a short commit SHA.\n"
                "It's recommended to use fully qualified 40-digit hashes though.\n"
                "Continue?"
            )
        fetch_commit_line = "git fetch {} {}".format(upstream, commit_sha)
        pending_mrg_line = 'git am "$(git format-patch -1 {} -o ../patches)"'.format(
            commit_sha
        )

        if pending_mrg_line in conf.get("shell_command_after", {}):
            ui.echo(
                "Requested pending merge is mentioned in {} already".format(
                    self.abs_merges_path
                )
            )
            return True
        if "shell_command_after" not in conf:
            conf["shell_command_after"] = CommentedSeq()

        # TODO propose a default comment format
        comment = ""
        if not skip_questions:
            comment = input(
                "Comment? " "(would appear just above new pending merge, optional):\n"
            )
        conf["shell_command_after"].extend([fetch_commit_line, pending_mrg_line])
        # Add a comment in the list of shell commands
        pos = conf["shell_command_after"].index(fetch_commit_line)
        conf["shell_command_after"].yaml_set_comment_before_after_key(
            pos, before=comment, indent=2
        )
        self.update_merges_config(conf)
        ui.echo(f"📋 cherry pick {upstream}/{commit_sha} has been added")
        return True

    def remove_pending_commit(self, upstream, commit_sha):
        conf = self.merges_config()
        lines_to_drop = [
            "git fetch {} {}".format(upstream, commit_sha),
            'git am "$(git format-patch -1 {} -o ../patches)"'.format(commit_sha),
        ]
        if lines_to_drop[0] not in conf.get(
            "shell_command_after", {}
        ) and lines_to_drop[1] not in conf.get("shell_command_after", {}):
            ui.exit_msg(
                "No such reference found in {},"
                " having troubles removing that:\n"
                "Looking for:\n- {}\n- {}".format(
                    self.abs_merges_path, lines_to_drop[0], lines_to_drop[1]
                )
            )
        for line in lines_to_drop:
            if line in conf["shell_command_after"]:
                conf["shell_command_after"].remove(line)
        if not conf["shell_command_after"]:
            del conf["shell_command_after"]
        self.update_merges_config(conf)
        print("✨ cherry pick {}/{} has been removed".format(upstream, commit_sha))

    def remove_pending_pull(self, upstream, pull_id):
        conf = self.merges_config()
        line_to_drop = "{} refs/pull/{}/head".format(upstream, pull_id)
        if line_to_drop not in conf["merges"]:
            ui.exit_msg(
                "No such reference found in {},"
                " having troubles removing that:\n"
                "Looking for: {}".format(self.abs_merges_path, line_to_drop)
            )
        conf["merges"].remove(line_to_drop)
        self.update_merges_config(conf)

    # aggregator API
    # TODO: add tests
    def get_aggregator(self, target_remote=None, target_branch=None, **extra_config):
        if "target" not in extra_config:
            extra_config["target"] = {}
        if target_branch and "branch" not in extra_config["target"]:
            extra_config["target"]["branch"] = target_branch
        if target_remote and "remote" not in extra_config["target"]:
            extra_config["target"]["remote"] = self.company_git_remote
        return RepoAggregator(self, **extra_config)

    # TODO: add tests
    def show_prs(self, state=None, purge=None):
        """Show all pull requests in pending merges.

        :param state: list only matching states
        :param purge: purge matching states
        """
        if purge:
            assert purge in ("closed", "merged")
        logging.getLogger("requests").setLevel(logging.ERROR)

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
        aggregator = self.get_aggregator()
        ui.echo("--")
        ui.echo(f"Checking: {self.name}")
        ui.echo(f"Path: {self.path}")
        ui.echo(f"Merge file: {self.merges_path}")
        all_prs = aggregator.collect_prs_info()
        if state is not None:
            # filter only our state
            all_prs = {k: v for k, v in all_prs.items() if k == state}
        for pr_state, prs in all_prs.items():
            ui.echo(f"State: {pr_state}")
            for i, pr_info in enumerate(prs, 1):
                all_repos_prs.setdefault(pr_state, []).append(pr_info)
                pr_info["raw"].update(pr_info)
                nr = str(i).zfill(2)
                pr = pr_info_msg.format(**pr_info["raw"])
                ui.echo(f"  {nr}) {pr}")
        if purge and all_repos_prs.get("closed", []):
            kw = {f"purge_{purge}": True}
            self._purge_closed_prs(all_repos_prs, **kw)
            # TODO: ask for re-aggregate?
        return all_repos_prs

    # TODO: add tests
    def _purge_closed_prs(self, all_repos_prs, purge_merged=False, purge_closed=False):
        assert purge_closed or purge_merged
        closed_prs = all_repos_prs.get("closed", [])
        closed_unmerged_prs = [
            pr for pr in closed_prs if pr.get("merged") == "not merged"
        ]
        closed_merged_prs = [pr for pr in closed_prs if pr.get("merged") == "merged"]

        # This list will receive all closed and unmerged pr's url to return
        # If purge_closed is set to True, removed prs will not be returned
        unmerged_prs_urls = [pr.get("url") for pr in closed_unmerged_prs]

        if closed_unmerged_prs and purge_closed:
            ui.echo("Purging closed ones...")
            for closed_pr_info in closed_unmerged_prs:
                try:
                    self.remove_pending(
                        closed_pr_info["owner"], closed_pr_info["shortcut"]
                    )
                    unmerged_prs_urls.remove(closed_pr_info.get("url"))
                except Exception as e:
                    ui.echo(
                        "An error occurs during '{}' removal : {}".format(
                            closed_pr_info.get("url"), e
                        )
                    )
        if closed_merged_prs and purge_merged:
            ui.echo("Purging merged ones...")
            for closed_pr_info in closed_merged_prs:
                self.remove_pending(closed_pr_info["owner"], closed_pr_info["shortcut"])
        return unmerged_prs_urls


class RepoAggregator(git_aggregator.repo.Repo):
    def __init__(self, repo, **extra_config):
        self.pm_repo = repo
        config = git_aggregator.config.load_config(self.pm_repo.abs_merges_path)[0]
        config.update(extra_config)
        super().__init__(**config)
        self.cwd = self.pm_repo.abs_path


def add_pending(entity_url):
    """Add a pending merge using given entity link"""
    # pattern, given an https://github.com/<user>/<repo>/pull/<pr-index>
    # # PR headline
    # # PR link as is
    # - refs/pull/<pr-index>/head
    parts = gh.parse_github_url(entity_url)
    upstream = parts.get("upstream")
    repo_name = parts.get("repo_name")
    entity_type = parts.get("entity_type")
    entity_id = parts.get("entity_id")

    repo = Repo(repo_name, path_check=False)
    if not repo.has_pending_merges():
        repo.generate_pending_merges_file_template(upstream)

    if entity_type == "pull":
        repo.add_pending_pull_request(upstream, entity_id)
    elif entity_type in ("commit", "tree"):
        repo.add_pending_commit(upstream, entity_id)
    return repo


def remove_pending(entity_url):
    parts = gh.parse_github_url(entity_url)
    upstream = parts.get("upstream")
    repo_name = parts.get("repo_name")
    repo = Repo(repo_name)
    entity_type = parts.get("entity_type")
    entity_id = parts.get("entity_id")

    if entity_type == "pull":
        repo.remove_pending_pull(upstream, entity_id)
    elif entity_type in ("tree", "commit"):
        repo.remove_pending_commit(upstream, entity_id)

    # check if that file is useless since it has an empty `merges` section
    # if it does - drop it instead of writing a new file version
    # only the upstream branch is present in `merges`
    # first item is `- oca 11.0` or similar
    config = repo.merges_config()
    pending_merges_present = len(config["merges"]) > 1
    patches = len(config.get("shell_command_after", {}))

    if not pending_merges_present and not patches:
        os.remove(repo.abs_merges_path)
    return repo


def make_merge_branch_name(version):
    project_id = get_project_manifest_key("project_id")
    branch_name = "merge-branch-{}-{}".format(project_id, version)
    return branch_name


def push_branches(version=None, force=False):
    """Push the local branches to the camptocamp remote

    The branch name will be composed of the id of the project and the current
    version number (the one in odoo/VERSION).

    It should be done at the closing of every release, so we are able
    to build a new patch branch from the same commits if required.
    """
    version = version or get_current_version()
    branch_name = make_merge_branch_name(version)
    if not force:
        # TODO
        gh.check_git_diff()

    # look through all of the files inside PENDING_MERGES_DIR, push everything
    impacted_repos = []
    company_git_remote = get_conf_key("company_git_remote")
    for repo in Repo.repositories_from_pending_folder():
        if not repo.has_pending_merges():
            continue
        config = repo.merges_config()
        impacted_repos.append(repo.path)
        ui.echo(f"Pushing {repo.path}")
        with cd(repo.abs_path):
            try:
                run("git config remote.{}.url".format(company_git_remote))
            except Exception:  # TODO
                remote_url = config["remotes"][company_git_remote]
                run("git remote add {} {}".format(company_git_remote, remote_url))
            run(
                "git push -f -v {} HEAD:refs/heads/{}".format(
                    company_git_remote, branch_name
                )
            )
    if impacted_repos:
        ui.echo("Impacted repos:")
        ui.echo("\n - ".join([x.as_posix() for x in impacted_repos]))
    else:
        ui.echo("No repo to push")
