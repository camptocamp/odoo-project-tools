# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import logging
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import click
import requests
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ..exceptions import PathNotFound
from ..utils.misc import SmartDict, get_docker_image_commit_hashes
from . import gh, git, ui
from .config import config
from .os_exec import run
from .path import build_path, cd
from .proj import get_project_id, get_project_manifest_key
from .yaml import (
    append_seq_item_with_comments,
    remove_seq_item_with_comments,
    sequence_item_indent,
    yaml_dump,
    yaml_load,
)

logger = logging.getLogger(__name__)


@dataclass(kw_only=True)
class PendingPR:
    """A pending-merge pull request, derived from the local merges file.

    The fields below ``is_patch`` are populated by
    :meth:`enrich_with_github`; until then ``state`` is ``None``.
    """

    _repo: "Repo"
    owner: str
    pr: int
    is_patch: bool
    # GitHub repo name; can differ from the local submodule directory name
    # (``self._repo.name``). Defaults to it when unspecified.
    repo: str | None = None
    # Filled in by enrich_with_github(); ``state is None`` means not yet enriched.
    state: str | None = None
    merged: bool = False
    labels: list[str] = field(default_factory=list)
    number: int | None = None
    title: str | None = None
    updated_at: str | None = None

    def __post_init__(self):
        if self.repo is None:
            self.repo = self._repo.name

    @property
    def shortcut(self) -> str:
        return f"{self.owner}/{self.repo}#{self.pr}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/pull/{self.pr}"

    @property
    def is_enriched(self) -> bool:
        return self.state is not None

    def to_dict(self) -> dict:
        """Return a JSON-friendly dict (with computed properties)."""
        return {
            "repo": self.repo,
            "owner": self.owner,
            "pr": self.pr,
            "is_patch": self.is_patch,
            "state": self.state,
            "merged": self.merged,
            "labels": self.labels,
            "number": self.number,
            "title": self.title,
            "updated_at": self.updated_at,
            "shortcut": self.shortcut,
            "url": self.url,
        }

    def enrich_with_github(self) -> None:
        """Fetch the PR's GitHub state and update this instance in place.

        Raises ``requests.RequestException`` (e.g. ``HTTPError`` on a rate-limit
        403, or a timeout/connection error) on failure; callers are expected to
        catch and decide how to surface it.
        """
        api_url = (
            f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{self.pr}"
        )
        headers = {}
        if token := os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"token {token}"
        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        self.state = data.get("state") or ""
        self.merged = bool(data.get("merged"))
        self.labels = [label["name"] for label in data.get("labels") or []]
        self.number = data.get("number")
        self.title = data.get("title")
        self.updated_at = data.get("updated_at")


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
        # TODO: proj_tmpl_ver=2 is deprecated
        elif self.template_version == 2 and submodule_name in ("odoo", "enterprise"):
            return self.odoo_src_rel_path / submodule_name
        return self.ext_src_rel_path / submodule_name

    def make_repo_merges_path(self, name_or_path, relative=False):
        """Return a pending-merges file for a given repo.

        :param name_or_path: either a full path or a bare repo name,
        as it is known at Github
        """
        repo_name = self._safe_repo_name(name_or_path)
        # TODO: proj_tmpl_ver=2 is deprecated (v1 has special handling below)
        if self.template_version == 1 and repo_name.lower() in ("odoo", "ocb"):
            repo_name = "src"
        base_path = self.pending_merge_abs_path
        if relative:
            base_path = self.pending_merge_rel_path
        return (base_path / repo_name).with_suffix(".yml")

    @classmethod
    def repositories_from_pending_folder(cls, path=None, path_check=True):
        pending_merge_abs_path = build_path(config.pending_merge_rel_path)
        path = Path(path or pending_merge_abs_path)
        return [cls(pth.stem, path_check=path_check) for pth in path.rglob("*.yml")]

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
        # TODO: proj_tmpl_ver=2 is deprecated (v1 has OCA/OCB handling below)
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
        default_target = f"merge-branch-{get_project_id()}-master"
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
        # TODO: proj_tmpl_ver=2 is deprecated
        elif self.template_version == 2:
            if self.name.lower() in ("odoo", "enterprise"):
                odoo_hash, enterprise_hash = get_docker_image_commit_hashes()
                hashes = {"odoo": odoo_hash, "enterprise": enterprise_hash}
                base_merge = f"{upstream} {hashes[self.name.lower()]}"

        config.insert(2, "merges", CommentedSeq([base_merge]))
        self.update_merges_config(config)
        git.submodule_set_url(self.path, remote_company_url)

    def update_pending_merges_file_base_merge(self, skip_questions: bool = False):
        """Checks that the base merge for an odoo/enterprise repository us up-to-date"""
        # TODO: proj_tmpl_ver=2 is deprecated (this method is v2-only)
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
        # TODO: proj_tmpl_ver=2 is deprecated
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
        data = response.json()
        base_branch = data.get("base", {}).get("ref")
        # Describe the new pending merge with its title + URL on the comment
        # lines above it, fetched from GitHub. When the call fails we simply skip
        # the comment (and the branch validation).
        comment = []
        if response.ok:
            if base_branch and base_branch != odoo_version:
                ui.ask_or_abort(
                    "Requested PR targets branch different from"
                    " current project's major version. Proceed?"
                )
            if title := data.get("title"):
                comment.append(title)
            if pr_url := data.get("html_url"):
                comment.append(pr_url)
        else:
            ui.echo(
                f"Github API call failed ({response.status_code}):"
                " skipping target branch validation."
            )

        known_remotes = conf["remotes"]
        if upstream not in known_remotes:
            known_remotes.insert(0, upstream, self.ssh_url(upstream))
        # Append the new pending merge at the end of the list, keeping the
        # comment blocks of the existing entries anchored to them, and aligning
        # the new comment with the merge items.
        append_seq_item_with_comments(
            conf["merges"],
            pending_mrg_line,
            comment=comment,
            comment_indent=sequence_item_indent(),
        )
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
        # TODO: proj_tmpl_ver=2 is deprecated
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
                remove_seq_item_with_comments(conf["shell_command_after"], line)
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
        remove_seq_item_with_comments(conf["merges"], line_to_drop)
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
                remove_seq_item_with_comments(patches, line)
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
    def run_aggregate(self, **kwargs):
        """Aggregate the pending merges using the git-aggregator CLI.

        The aggregation happens on the local branch declared as ``target`` in
        the merges file, which acts as a local scratch branch: pushing the
        result to a permanent, dynamically named remote branch is handled
        separately by :meth:`push_to_remote`.

        Extra keyword arguments are passed through to :func:`run`.
        """
        # The merges file keys are paths relative to the pending-merges
        # folder (e.g. ``../odoo/external-src/<name>``), and gitaggregate
        # resolves them against the process working directory.
        kwargs.setdefault("cwd", self.pending_merge_abs_path)
        kwargs.setdefault("check", True)
        kwargs.setdefault("verbose", True)
        run(
            ["gitaggregate", "--config", str(self.abs_merges_path), "aggregate"],
            **kwargs,
        )

    def _iter_pending_pull_requests(self) -> Iterator[PendingPR]:
        merges_config = self.merges_config()
        if not merges_config:
            return
        remotes = merges_config.get("remotes") or {}
        # Skip the first ``merges`` entry, which is the base ref (e.g. ``OCA 16.0``)
        for merge_line in list(merges_config.get("merges") or [])[1:]:
            parts = str(merge_line).split()
            if len(parts) != 2:
                continue
            remote, ref = parts
            pull_match = re.match(r"^(?:refs/)?pull/(\d+)/head$", ref)
            if not pull_match:
                continue
            try:
                owner, github_repo = gh.parse_remote_url(remotes.get(remote, ""))
            except ValueError:
                owner = remote
                github_repo = self.name
            yield PendingPR(
                _repo=self,
                owner=owner,
                repo=github_repo,
                pr=int(pull_match.group(1)),
                is_patch=False,
            )
        for line in merges_config.get("shell_command_after") or []:
            if ".patch" not in line or "git am" not in line:
                continue
            url = line.split(".patch")[0]
            try:
                info = gh.parse_github_url(url)
            except ValueError:
                continue
            yield PendingPR(
                _repo=self,
                owner=info["upstream"],
                repo=info["repo_name"],
                pr=int(info["entity_id"]),
                is_patch=True,
            )

    def purge_merged_prs(self) -> Iterator[PendingPR]:
        """Remove merged pull requests from the pending-merges file.

        Iterates the local pending-merges, enriches each one via the GitHub
        API, and yields the merged ones as soon as they are removed so that
        callers can report progress in real time.

        A PR whose GitHub status can't be fetched (rate limit, timeout, …) is
        left in place: we can't tell whether it was merged, so removing it
        would be unsafe.
        """
        for pr in self._iter_pending_pull_requests():
            try:
                pr.enrich_with_github()
            except requests.RequestException as exc:
                logger.warning("Could not get status of %s: %s", pr.shortcut, exc)
                continue
            if not pr.merged:
                continue
            if pr.is_patch:
                self.remove_pending_pull_from_patches(pr.owner, pr.pr)
            else:
                self.remove_pending_pull(pr.owner, pr.pr)
            yield pr
        if not self.has_any_pr_left():
            self._handle_empty_merges_file(delete_file=True)

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
            remotes = git.get_remotes(self.abs_path)
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

    def push_to_remote(self, target_branch=None):
        """Push the aggregated HEAD to the company remote as ``target_branch``.

        The branch name embeds the project commit hash, giving the aggregated
        commit a permanent ref on the fork so that submodule pins referencing
        it always stay fetchable.
        """
        target_branch = target_branch or gh.get_target_branch()
        git.ensure_remote(
            self.abs_path,
            self.company_git_remote,
            self.ssh_url(self.company_git_remote),
        )
        run(
            f"git push -f {self.company_git_remote} HEAD:refs/heads/{target_branch}",
            cwd=self.abs_path,
            check=True,
            verbose=True,
        )

    def rebuild_consolidation_branch(self, push=False):
        self.run_aggregate()
        if push:
            self.push_to_remote()


def add_pending(entity_url, aggregate=True, patch=False, push=True):
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

    # TODO: proj_tmpl_ver=2 is deprecated
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
        repo.run_aggregate()
        if push:
            repo.push_to_remote()
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
    if not repo.has_any_pr_left():
        repo._handle_empty_merges_file(delete_file=True)
    elif aggregate:
        repo.run_aggregate()
    return repo


def make_merge_branch_name(version):
    project_id = get_project_id()
    branch_name = f"merge-branch-{project_id}-{version}"
    return branch_name


def get_new_remote_url(repo: Repo, force_remote: str | bool = False):
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
