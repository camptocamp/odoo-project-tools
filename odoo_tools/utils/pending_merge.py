# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from pathlib import PosixPath

import git_aggregator.config
import git_aggregator.main
import git_aggregator.repo
import requests

# FIXME: move to yaml utils
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ..config import get_conf_key
from ..exceptions import PathNotFound
from . import ui
from .gh import parse_github_url
from .path import build_path
from .proj import get_project_manifest_key
from .yaml import yaml_load

git_aggregator.main.setup_logger()


# FIXME: move to yaml utils
yaml = YAML()


try:
    input = raw_input
except NameError:
    pass

BRANCH_EXCLUDE = """
branches:
  except:
    - /^merge-branch-.*$/
"""

git_aggregator.main.setup_logger()


class Repo:
    """Handle checked out repositories and their pending merges."""

    def __init__(self, name_or_path, path_check=True):
        self.c2c_git_remote = get_conf_key("c2c_git_remote")
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
            yaml.dump(data, f)

    def api_url(self):
        return "https://api.github.com/repos/{}/{}".format(
            self.c2c_git_remote, self.name
        )

    def ssh_url(self, namespace=None):
        namespace = namespace or self.c2c_git_remote
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
        remote_c2c_url = self.ssh_url()
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

        if upstream != self.c2c_git_remote:
            # if origin is not the same: add c2c one
            remotes.insert(0, self.c2c_git_remote, remote_c2c_url)
        config = CommentedMap()
        config.insert(0, "remotes", remotes)
        config.insert(1, "target", "{} {}".format(self.c2c_git_remote, default_target))
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
            ui.exit_msg(
                "Requested pending merge is already mentioned in {} ".format(
                    self.abs_merges_path
                )
            )

        response = requests.get("{}/pulls/{}".format(self.api_url(), pull_id))

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
            print(
                "Github API call failed ({}):"
                " skipping target branch validation.".format(response.status_code)
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
            ui.exit_msg(
                "Requested pending merge is mentioned in {} already".format(
                    self.abs_merges_path
                )
            )
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
        print("📋 cherry pick {}/{} has been added".format(upstream, commit_sha))

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
            extra_config["target"]["remote"] = self.c2c_git_remote
        return RepoAggregator(self, **extra_config)


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
    parts = parse_github_url(entity_url)
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
    parts = parse_github_url(entity_url)
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
