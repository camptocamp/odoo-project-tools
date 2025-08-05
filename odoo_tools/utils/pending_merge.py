# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import logging
from pathlib import Path

import click
import git_aggregator.config
import git_aggregator.main
import git_aggregator.repo
import requests
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ..exceptions import PathNotFound
from ..utils.misc import SmartDict, get_docker_image_commit_hashes
from . import gh, git, ui
from .config import config
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
        self.template_version = config.template_version or 1
        self.company_git_remote = config.company_git_remote
        self.odoo_src_rel_path = config.odoo_src_rel_path
        self.ext_src_rel_path = config.ext_src_rel_path
        self.pending_merge_rel_path = config.pending_merge_rel_path
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
                f"{self.abs_path} does not look like a mature repository. "
                "Aborting."
            )
        if not self.abs_merges_path.exists():
            raise PathNotFound(f"MERGES PATH NOT FOUND `{self.abs_merges_path}'.")

    @staticmethod
    def _safe_repo_name(name_or_path):
        return Path(name_or_path).name

    def make_repo_path(self, name_or_path):
        """Return a submodule path by a submodule name."""
        submodule_name = self._safe_repo_name(name_or_path)
        if self.template_version == 1 and submodule_name in ("odoo", "ocb", "src"):
            return self.odoo_src_rel_path
        elif self.template_version == 2 and submodule_name in ("odoo", "enterprise"):
            return self.odoo_src_rel_path / submodule_name
        return self.ext_src_rel_path / submodule_name

    def make_repo_merges_path(self, name_or_path, relative=False):
        """Return a pending-merges file for a given repo.

        :param name_or_path: either a full path or a bare repo name,
        as it is known at Github
        """
        repo_name = self._safe_repo_name(name_or_path)
        if self.template_version == 1 and repo_name.lower() in ("odoo", "ocb"):
            repo_name = "src"
        base_path = self.pending_merge_abs_path
        if relative:
            base_path = self.pending_merge_rel_path
        return (base_path / repo_name).with_suffix(".yml")

    @classmethod
    def repositories_from_pending_folder(cls, path=None):
        pending_merge_abs_path = build_path(config.pending_merge_rel_path)
        path = Path(path or pending_merge_abs_path)
        return [cls(pth.stem) for pth in path.rglob("*.yml")]

    def has_pending_merges(self):
        # either empty or commented out
        return bool(self.abs_merges_path.exists() and self.merges_config())

    def has_any_pr_left(self):
        if not self.has_pending_merges():
            return False
        config = self.merges_config()
        pr_refs = any("pull" in x for x in config.get("merges", []))
        patches = config.get("shell_command_after", []) or []
        pr_patches = any("pull" in x for x in patches)
        return pr_refs or pr_patches

    def merges_config(self):
        data = yaml_load(self.abs_merges_path.read_text()) or {}
        # FIXME: this should be relative
        # to the position of the pending merge folder
        repo_relpath = ".." / self.path
        return data.get(repo_relpath.as_posix(), {})

    def update_merges_config(self, config):
        # get former config if any
        if self.abs_merges_path.exists():
            data = yaml_load(self.abs_merges_path.read_text())
        else:
            data = {}
        data[(".." / self.path).as_posix()] = config
        with self.abs_merges_path.open("w") as fobj:
            yaml_dump(data, fobj)

    def api_url(self, upstream=None):
        return f"https://api.github.com/repos/{upstream or self.company_git_remote}/{self.name}"

    def ssh_url(self, namespace=None):
        namespace = namespace or self.company_git_remote
        return self.build_ssh_url(namespace, self.name)

    @classmethod
    def build_ssh_url(cls, namespace, repo_name):
        return f"git@github.com:{namespace}/{repo_name}.git"

    def generate_pending_merges_file_template(self, upstream):
        """Create git-aggregator config for current repo"""
        # could be that this is the first PM ever added to this project
        self.pending_merge_abs_path.mkdir(parents=True, exist_ok=True)

        oca_ocb_remote = False
        if (
            self.template_version == 1
            and upstream.lower() == "odoo"
            and self.path == self.odoo_src_rel_path
        ):
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
        config.insert(1, "target", f"{self.company_git_remote} {default_target}")

        base_merge = f"{upstream} {odoo_version}"
        if self.template_version == 1:
            if oca_ocb_remote:
                base_merge = "{} {}".format("oca", odoo_version)
        elif self.template_version == 2:
            if self.name.lower() in ("odoo", "enterprise"):
                odoo_hash, enterprise_hash = get_docker_image_commit_hashes()
                hashes = {"odoo": odoo_hash, "enterprise": enterprise_hash}
                base_merge = f"{upstream} {hashes[self.name.lower()]}"

        config.insert(2, "merges", CommentedSeq([base_merge]))
        self.update_merges_config(config)

    def update_pending_merges_file_base_merge(self, skip_questions: bool = False):
        """Checks that the base merge for an odoo/enterprise repository us up-to-date"""
        if self.template_version == 1:
            return
        if self.name.lower() not in ("odoo", "enterprise"):
            return
        if not self.has_pending_merges():
            return
        # Get the image commit hashes
        odoo_hash, enterprise_hash = get_docker_image_commit_hashes()
        hashes = {"odoo": odoo_hash, "enterprise": enterprise_hash}
        # Get the pending merge base merge reference
        config = self.merges_config()
        base_merge = config["merges"][0]
        upstream, ref = base_merge.split()
        # Check if the base merge is up-to-date
        if upstream == "odoo" and ref == hashes[self.name.lower()]:
            return
        # Ask confirmation is required
        if not skip_questions and not click.confirm(
            f"The base merge for {self.name} ({base_merge}) is not up-to-date.\n"
            f"The base image current hash is {hashes[self.name.lower()]}.\n"
            f"Do you want to update it?",
            default=True,
        ):
            return
        # Update it
        config["merges"][0] = f"{upstream} {hashes[self.name.lower()]}"
        self.update_merges_config(config)

    def add_pending_pull_request(self, upstream, pull_id):
        if self.template_version == 2 and self.name.lower() in ("odoo", "enterprise"):
            ui.exit_msg(
                "Sorry, adding a pending Pull Request to Odoo repositories is not "
                "supported. Please add a pending commit instead."
            )
        conf = self.merges_config()
        odoo_version = get_project_manifest_key("odoo_version")
        pending_mrg_line = f"{upstream} refs/pull/{pull_id}/head"
        if pending_mrg_line in conf.get("merges", {}):
            ui.echo(
                f"Requested pending merge is already mentioned in {self.abs_merges_path} "
            )
            return True

        response = requests.get(f"{self.api_url(upstream=upstream)}/pulls/{pull_id}")

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

    def add_pending_pull_request_patch(self, upstream, entity_url):
        conf = self.merges_config()
        line = f"curl -sSL {entity_url} | git am -3 --keep-non-patch --exclude '*requirements.txt'"
        patches = self.merges_config().get("shell_command_after") or []
        if line in patches:
            ui.echo(
                f"{self.abs_merges_path} already contains a reference to {entity_url}"
            )
            return
        patches.append(line)
        conf["shell_command_after"] = patches
        self.update_merges_config(conf)
        ui.echo(f"📋 patch {entity_url} has been added")

    def _get_pending_commit_lines(self, upstream: str, commit_sha: str):
        """Return the lines to add to the merges file for a given commit."""
        if self.template_version == 1:
            return [
                f"git fetch {upstream} {commit_sha}",
                f'git am "$(git format-patch -1 {commit_sha} -o ../patches)"',
            ]
        # self.template_version == 2
        if self.name.lower() in ("odoo", "enterprise"):
            # For Odoo repositories, we store the patch in a subdirectory
            # This patch will be applied when the image is built.
            patch_dir = f"../../patches/{self.name}"
            return [
                f"git fetch {upstream} {commit_sha}",
                f'git am "$(git format-patch -1 {commit_sha} -o {patch_dir})"',
            ]
        else:
            # For external repositories, we just cherry-pick the commit,
            # as we don't need to store the patch file.
            return [
                f"git fetch {upstream} {commit_sha}",
                f"git cherry-pick {commit_sha}",
            ]

    def add_pending_commit(self, upstream, commit_sha, skip_questions=True):
        conf = self.merges_config()
        # TODO search in local git history for full hash
        if len(commit_sha) < 40:
            ui.ask_or_abort(
                "You are about to add a patch referenced by a short commit SHA.\n"
                "It's recommended to use fully qualified 40-digit hashes though.\n"
                "Continue?"
            )
        fetch_commit_line, pending_mrg_line = self._get_pending_commit_lines(
            upstream, commit_sha
        )

        if pending_mrg_line in conf.get("shell_command_after", {}):
            ui.echo(
                f"Requested pending merge is mentioned in {self.abs_merges_path} already"
            )
            return True
        if "shell_command_after" not in conf:
            conf["shell_command_after"] = CommentedSeq()

        # TODO propose a default comment format
        comment = ""
        if not skip_questions:
            comment = input(
                "Comment? (would appear just above new pending merge, optional):\n"
            )
        conf["shell_command_after"].extend([fetch_commit_line, pending_mrg_line])
        # Add a comment in the list of shell commands
        if comment:
            pos = conf["shell_command_after"].index(fetch_commit_line)
            conf["shell_command_after"].yaml_set_comment_before_after_key(
                pos, before=comment, indent=2
            )
        self.update_merges_config(conf)
        ui.echo(f"📋 cherry pick {upstream}/{commit_sha} has been added")
        return True

    def remove_pending_commit(self, upstream, commit_sha):
        conf = self.merges_config()
        lines_to_drop = self._get_pending_commit_lines(upstream, commit_sha)
        if lines_to_drop[0] not in conf.get(
            "shell_command_after", {}
        ) and lines_to_drop[1] not in conf.get("shell_command_after", {}):
            ui.exit_msg(
                f"No such reference found in {self.abs_merges_path},"
                " having troubles removing that:\n"
                f"Looking for:\n- {lines_to_drop[0]}\n- {lines_to_drop[1]}"
            )
        for line in lines_to_drop:
            if line in conf["shell_command_after"]:
                conf["shell_command_after"].remove(line)
        if not conf["shell_command_after"]:
            del conf["shell_command_after"]
        self.update_merges_config(conf)
        print(f"✨ cherry pick {upstream}/{commit_sha} has been removed")

    def remove_pending_pull(self, upstream, pull_id):
        conf = self.merges_config()
        line_to_drop = f"{upstream} refs/pull/{pull_id}/head"
        if line_to_drop not in conf["merges"]:
            ui.exit_msg(
                f"No such reference found in {self.abs_merges_path},"
                " having troubles removing that:\n"
                f"Looking for: {line_to_drop}"
            )
        conf["merges"].remove(line_to_drop)
        self.update_merges_config(conf)

    def remove_pending_pull_from_patches(self, upstream, pull_id):
        conf = self.merges_config()
        patches = conf.get("shell_command_after") or []
        if not patches:
            return
        line_bit_to_drop = f"pull/{pull_id}.patch"
        found = False
        for line in patches:
            if line_bit_to_drop in line:
                patches.remove(line)
                found = True
                break
        if not found:
            ui.exit_msg(
                f"No such reference found in {self.abs_merges_path},"
                " having troubles removing that:\n"
                f"Looking for: {line_bit_to_drop}"
            )
        conf["shell_command_after"] = patches if patches else None
        self.update_merges_config(conf)

    # aggregator API
    # TODO: add tests
    def get_aggregator(self, target_remote=None, target_branch=None, **extra_config):
        if "target" not in extra_config:
            extra_config["target"] = {}
        target_branch = target_branch or gh.get_target_branch()
        if target_branch and "branch" not in extra_config["target"]:
            extra_config["target"]["branch"] = target_branch
        target_remote = target_remote or self.company_git_remote
        if target_remote and "remote" not in extra_config["target"]:
            extra_config["target"]["remote"] = target_remote
        return RepoAggregator(self, **extra_config)

    # TODO: add tests
    def show_prs(self, state=None, purge=None, yes_all=False):
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
        ui.echo("--")
        ui.echo(f"Checking: {self.name}")
        ui.echo(f"Path: {self.path}")
        ui.echo(f"Merge file: {self.merges_path}")

        all_prs = self._collect_prs()

        if state is not None:
            if state == "merged":
                all_prs = {"closed": all_prs.get("closed", [])}
                all_prs["closed"] = [
                    pr for pr in all_prs["closed"] if pr.get("merged") == "merged"
                ]
            else:
                all_prs = {k: v for k, v in all_prs.items() if k == state}
        for pr_state, prs in all_prs.items():
            ui.echo(f"State: {pr_state}")
            for i, pr_info in enumerate(prs, 1):
                all_repos_prs.setdefault(pr_state, []).append(pr_info)
                pr_info["raw"].update(pr_info)
                nr = str(i).zfill(2)
                pr = pr_info_msg.format(**pr_info["raw"])
                ui.echo(f"  {nr}) {pr}")

        purged = None
        if purge and all_repos_prs.get("closed", []):
            kw = {f"purge_{purge}": True}
            purged = self._purge_closed_prs(all_repos_prs, **kw)

        if purged and self.has_pending_merges():
            if yes_all or ui.ask_confirmation("Do you want to re-aggregate and push?"):
                aggregator = self.get_aggregator()
                aggregator.aggregate()
                aggregator.push()
        if not self.has_any_pr_left():
            self._handle_empty_merges_file(delete_file=yes_all)
        return all_repos_prs

    def _collect_prs(self):
        aggregator = self.get_aggregator()
        # Normal merges
        all_prs = aggregator.collect_prs_info()
        # patches
        patch_merges = []
        # Convert lines like:
        # "curl -sSL https://github.com/OCA/manufacture/pull/1469.patch
        # | git am -3 --keep-non-patch --exclude '*requirements.txt'"
        # ...to...
        # OCA refs/pull/1469/head
        patches = self.merges_config().get("shell_command_after") or []
        if not patches:
            return all_prs
        for line in patches:
            if ".patch" in line and "git am" in line:
                line = line.split(".patch")[0]
                pr_info = gh.parse_github_url(line)
                patch_merges.append(
                    {
                        "remote": pr_info["upstream"],
                        "ref": f"refs/{pr_info['entity_type']}/{pr_info['entity_id']}/head",
                    }
                )
        patch_merges = aggregator.collect_prs_info(merges=patch_merges)
        for state, prs in patch_merges.items():
            for pr_info in prs:
                pr_info["_patch"] = True
            all_prs.setdefault(state, []).extend(prs)
        return all_prs

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

        purged = False
        if closed_unmerged_prs and purge_closed:
            ui.echo("Purging closed ones...")
            for closed_pr_info in closed_unmerged_prs:
                try:
                    if closed_pr_info.get("_patch"):
                        self.remove_pending_pull_from_patches(
                            closed_pr_info["owner"], closed_pr_info["pr"]
                        )
                    else:
                        self.remove_pending_pull(
                            closed_pr_info["owner"], closed_pr_info["pr"]
                        )
                    unmerged_prs_urls.remove(closed_pr_info.get("url"))
                    purged = True
                except Exception as e:
                    ui.echo(
                        "An error occurs during '{}' removal : {}".format(
                            closed_pr_info.get("url"), e
                        )
                    )
        if closed_merged_prs and purge_merged:
            ui.echo("Purging merged ones...")
            for closed_pr_info in closed_merged_prs:
                if closed_pr_info.get("_patch"):
                    self.remove_pending_pull_from_patches(
                        closed_pr_info["owner"], closed_pr_info["pr"]
                    )
                else:
                    self.remove_pending_pull(
                        closed_pr_info["owner"], closed_pr_info["pr"]
                    )
                purged = True
        return purged

    def _handle_empty_merges_file(self, delete_file=False):
        odoo_version = get_project_manifest_key("odoo_version")
        ui.echo("")
        update_options = [
            SmartDict(choice="9", label="no update", remote="", ref=""),
        ]
        default_remote = "OCA"
        avail_remotes = list(self.merges_config()["remotes"].keys())
        if "OCA" not in avail_remotes:
            if self.company_git_remote in avail_remotes:
                default_remote = self.company_git_remote
            else:
                ui.exit_msg("No OCA or company remote found in merges config.")

        for i, remote in enumerate(avail_remotes, start=1):
            ref = f"{remote}/{odoo_version}"
            update_options.append(
                SmartDict(
                    choice=str(i),
                    label=ref,
                    remote=remote,
                    ref=ref,
                    default=remote == default_remote,
                )
            )
        sorted_options = sorted(update_options, key=lambda x: x.choice)
        default_choice = next(opt for opt in sorted_options if opt.default).choice
        msg = (
            f"Submodule {self.name} has no pending merges. "
            f"Choose if/how to update:\n"
            + "\n".join([f"  {opt.choice}) {opt.label} " for opt in sorted_options])
            + "\n"
        )
        if delete_file:
            choice = default_choice
        else:
            choice = ui.ask_question(msg, default=default_choice)
        opt = next(opt for opt in sorted_options if opt.choice == choice)
        if opt.remote:
            # FIXME: use an internal util to get remotes
            remotes = self.get_aggregator()._get_remotes()
            new_remote_url = get_new_remote_url(repo=self, force_remote=opt.remote)
            if opt.remote not in remotes:
                ui.echo(f"Adding missing remote: {opt.remote} -> {new_remote_url}")
                git.set_remote_url(
                    self.path, new_remote_url, remote=opt.remote, add=True
                )
            else:
                # Sync submodule conf
                ui.echo(f"Updating submodule conf: {opt.remote} -> {new_remote_url}")
                git.submodule_set_url(self.path, new_remote_url, remote=opt.remote)
            with cd(self.abs_path):
                git.checkout(odoo_version, remote=opt.remote)
        ui.echo("")
        if delete_file or ui.ask_confirmation(
            f"Delete pending merge file {self.abs_merges_path}?"
        ):
            self.abs_merges_path.unlink()

    def rebuild_consolidation_branch(self, push=False):
        aggregator = self.get_aggregator()
        aggregator.aggregate()
        if push:
            aggregator.push()


class RepoAggregator(git_aggregator.repo.Repo):
    def __init__(self, repo, **extra_config):
        self.pm_repo = repo
        config = git_aggregator.config.load_config(self.pm_repo.abs_merges_path)[0]
        config.update(extra_config)
        super().__init__(**config)
        self.cwd = self.pm_repo.abs_path


def add_pending(entity_url, aggregate=True, patch=False):
    """Add a pending merge using the given entity url.

    Adds the pending merge in the appropriate aggregation file (under pending-merges.d),
    creating a new file if necessary. Optionally run git aggregate using that file.

    :param entity_url: url of a pull request (e.g. https://github.com/<user>/<repo>/pull/<pr-index>)
    :param aggregate: if True, run git aggregate after editing the file
    """
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

    if repo.template_version == 2:
        repo.update_pending_merges_file_base_merge()

    if entity_type == "pull":
        if entity_url.endswith(".patch"):
            patch = True
        elif patch and not entity_url.endswith(".patch"):
            entity_url += ".patch"
        if patch:
            repo.add_pending_pull_request_patch(upstream, entity_url)
        else:
            repo.add_pending_pull_request(upstream, entity_id)
    elif entity_type in ("commit", "tree"):
        repo.add_pending_commit(upstream, entity_id)
    if aggregate:
        aggregator = repo.get_aggregator()
        aggregator.aggregate()
    return repo


def remove_pending(entity_url, aggregate=True):
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
        repo.abs_merges_path.unlink()
    if aggregate:
        aggregator = repo.get_aggregator()
        aggregator.aggregate()
    return repo


def make_merge_branch_name(version):
    project_id = get_project_manifest_key("project_id")
    branch_name = f"merge-branch-{project_id}-{version}"
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
    company_git_remote = config.company_git_remote
    for repo in Repo.repositories_from_pending_folder():
        if not repo.has_pending_merges():
            continue
        merges_config = repo.merges_config()
        impacted_repos.append(repo.path)
        ui.echo(f"Pushing {repo.path}")
        with cd(repo.abs_path):
            try:
                run(f"git config remote.{company_git_remote}.url")
            except Exception:  # TODO
                remote_url = merges_config["remotes"][company_git_remote]
                run(f"git remote add {company_git_remote} {remote_url}")
            run(f"git push -f -v {company_git_remote} HEAD:refs/heads/{branch_name}")
    if impacted_repos:
        ui.echo("Impacted repos:")
        ui.echo("\n - ".join([x.as_posix() for x in impacted_repos]))
    else:
        ui.echo("No repo to push")


def get_new_remote_url(repo=None, force_remote=False):
    if repo.has_pending_merges():
        with repo.abs_merges_path.open() as pending_merges:
            # read everything we can reach
            # for reading purposes only
            data = yaml_load(pending_merges)
            submodule_pending_config = data[(Path("..") / repo.path).as_posix()]
            merges_in_action = submodule_pending_config["merges"]
            registered_remotes = submodule_pending_config["remotes"]

            if force_remote:
                new_remote_url = registered_remotes[force_remote]
            elif merges_in_action:
                new_remote_url = registered_remotes[repo.company_git_remote]
            else:
                new_remote_url = next(
                    remote
                    for remote in registered_remotes.values()
                    if remote != repo.company_git_remote
                )
    else:
        # resolve what's the parent repository
        # from which company remote consolidation was forked
        response = requests.get(repo.api_url())
        if response.ok:
            info = response.json()
            parent = info.get("parent", {})
            if parent:
                new_remote_url = parent.get("ssh_url")
            else:
                # not a forked repo (eg: camptocamp/connector-jira)
                new_remote_url = info.get("ssh_url")
        else:
            ui.echo(
                "Couldn't reach Github API to resolve submodule upstream."
                " Please provide it manually."
            )
            default_repo = repo.name.replace("_", "-")
            new_namespace = input("Namespace [OCA]: ") or "OCA"
            new_repo = input(f"Repo name [{default_repo}]: ") or default_repo
            new_remote_url = Repo.build_ssh_url(new_namespace, new_repo)

    return new_remote_url
