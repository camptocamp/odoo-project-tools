# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import datetime
from pathlib import Path
from unittest import mock

import git
import pytest

from odoo_tools.cli import release
from odoo_tools.cli.project import init
from odoo_tools.utils.config import config
from odoo_tools.utils.git import tag_signing_enabled

from .common import compare_line_by_line, mock_pending_merge_repo_paths


def git_commit_all(message="commit"):
    """Commit everything in the working tree, to get a clean starting point."""
    repo = git.Repo(".")
    repo.git.add("-A")
    repo.git.commit("--message", message)


def test_make_towncrier_cmd():
    cmd = release.make_towncrier_cmd("16.0.1.0.0")
    assert cmd == "towncrier build --yes --version=16.0.1.0.0"


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump(project):
    ver_file = config.version_file_rel_path
    assert ver_file.read_text() == "14.0.0.1.0"
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    # the commit flow requires a clean tree to start from
    git_commit_all()

    def bump(*args):
        # --commit --tag exercises the full release path without prompting;
        # the bump auto-commits, so no manual git_commit_all is needed between calls.
        project.invoke(
            release.bump,
            [*args, "--commit", "--tag"],
            catch_exceptions=False,
            input="n",
        )

    bump("patch")
    assert ver_file.read_text() == "14.0.0.1.1"
    bump("minor")
    assert ver_file.read_text() == "14.0.0.2.0"
    bump("major")
    assert ver_file.read_text() == "14.0.1.0.0"
    bump("minor")
    assert ver_file.read_text() == "14.0.1.1.0"
    bump("patch")
    assert ver_file.read_text() == "14.0.1.1.1"
    bump("major")
    assert ver_file.read_text() == "14.0.2.0.0"
    bump("major", "--new-version", "15.0.0.0.1")
    assert ver_file.read_text() == "15.0.0.0.1"


@pytest.mark.project_setup(
    proj_version="14.0.1.2.0", mock_marabunta_file=True, git_init=True
)
def test_bump_wrong_parameters(project):
    ver_file = config.version_file_rel_path
    assert ver_file.read_text() == "14.0.1.2.0"
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    # bump should fail because there's too many parameters
    result = project.invoke(release.bump, ["--type", "patch"])
    assert result.exit_code > 0
    assert "No such option" in result.output
    result = project.invoke(release.bump, ["patch", "major"])
    assert result.exit_code > 0
    assert "Got unexpected extra argument" in result.output
    assert ver_file.read_text() == "14.0.1.2.0"


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_changelog(project):
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    hist_part_1 = (
        ".. :changelog:\n"
        ".. DO NOT EDIT. File is generated from fragments.\n\n"
        "Release History\n"
        "---------------\n\n"
        ".. towncrier release notes start\n\n"
    )
    hist_part_2 = "14.0.0.1.0 (2011-10-09)\n+++++++++++++++++++++++\n\n* Blah\n"
    cwd = Path()
    (cwd / "changes.d/1234.bug").write_text("Fixed a thing!")
    (cwd / "changes.d/2345.feat").write_text("Added a thing!")
    (cwd / "HISTORY.rst").write_text(hist_part_1 + hist_part_2)
    result = project.invoke(
        release.bump,
        ["minor", "--no-commit", "--no-tag"],
        catch_exceptions=False,
        input="n",
    )
    new_part = (
        f"14.0.0.2.0 ({datetime.date.today():%Y-%m-%d})\n"
        "+++++++++++++++++++++++\n\n"
        "**Features and Improvements**\n"
        "* 2345: Added a thing!\n\n"
        "**Bugfixes**\n"
        # Note the 2 empty lines to separate versions
        "* 1234: Fixed a thing!\n\n\n"
    )

    compare_line_by_line(
        (cwd / "HISTORY.rst").read_text(),
        hist_part_1 + new_part + hist_part_2,
    )
    assert result.output.splitlines()[0].startswith("Running: bump-my-version bump")
    assert "Running: towncrier build --yes --version=14.0.0.2.0" in result.output
    assert result.exit_code == 0


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_update_marabunta_file(project):
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    result = project.invoke(
        release.bump,
        ["minor", "--no-commit", "--no-tag"],
        catch_exceptions=False,
        input="n",
    )
    content = config.marabunta_mig_file_rel_path.read_text()
    assert "14.0.0.2.0" in content
    assert result.output.splitlines()[0].startswith("Running: bump-my-version bump")
    assert "Running: towncrier build --yes --version=14.0.0.2.0" in result.output
    assert result.exit_code == 0


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0",
    proj_cfg=dict(marabunta_mig_file_rel_path=None),
    mock_marabunta_file=False,
    git_init=True,
)
def test_bump_update_without_marabunta_file(project):
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    result = project.invoke(
        release.bump,
        ["minor", "--no-commit", "--no-tag"],
        catch_exceptions=False,
        input="n",
    )
    assert result.output.splitlines()[0].startswith("Running: bump-my-version bump")
    assert "Running: towncrier build --yes --version=14.0.0.2.0" in result.output
    assert result.exit_code == 0


@pytest.mark.project_setup(
    proj_version="18.0.0.0.0",
    proj_cfg={"version_file_rel_path": None},
    mock_marabunta_file=True,
    git_init=True,
)
def test_bump_without_version_file_and_no_bundle_addon(project):
    # run init to get all files ready
    project.invoke(init, catch_exceptions=False)
    git_commit_all()
    # check that the version file is not present
    assert config.version_file_rel_path is None
    # bump should fail because there are no files to bump
    result = project.invoke(release.bump, ["minor"])
    assert result.exit_code != 0
    assert "No files to bump" in result.output


@pytest.mark.project_setup(
    proj_version="18.0.1.2.0",
    mock_marabunta_file=True,
    mock_bundle_addon=True,
    git_init=True,
)
def test_bump_bundle_addon_manifest_version(project):
    # make sure the bundle addon is created
    bundle_addon_path = config.local_src_rel_path / "acme_bundle"
    assert bundle_addon_path.is_dir()
    assert (bundle_addon_path / "__manifest__.py").is_file()
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    # bump the version
    result = project.invoke(
        release.bump,
        ["minor", "--no-commit", "--no-tag"],
        catch_exceptions=False,
        input="n",
    )
    assert result.output.splitlines()[0].startswith("Running: bump-my-version bump")
    assert "Running: towncrier build --yes --version=18.0.1.3.0" in result.output
    assert result.exit_code == 0
    # make sure the bundle addon version is updated in both files
    assert "18.0.1.3.0" in (bundle_addon_path / "__manifest__.py").read_text()
    assert "18.0.1.3.0" == (config.version_file_rel_path).read_text()


@pytest.mark.project_setup(
    proj_version="18.0.1.2.0",
    proj_cfg={"version_file_rel_path": None},
    mock_marabunta_file=True,
    mock_bundle_addon=True,
    git_init=True,
)
def test_bump_bundle_addon_manifest_version_without_version_file(project):
    # make sure the bundle addon is created
    bundle_addon_path = config.local_src_rel_path / "acme_bundle"
    assert bundle_addon_path.is_dir()
    assert (bundle_addon_path / "__manifest__.py").is_file()
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    # bump the version
    result = project.invoke(
        release.bump,
        ["minor", "--no-commit", "--no-tag"],
        catch_exceptions=False,
        input="n",
    )
    assert result.output.splitlines()[0].startswith("Running: bump-my-version bump")
    assert "Running: towncrier build --yes --version=18.0.1.3.0" in result.output
    assert result.exit_code == 0
    # make sure the bundle addon version is updated in both files
    assert "18.0.1.3.0" in (bundle_addon_path / "__manifest__.py").read_text()


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_push_no_repo(project):
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    result = project.invoke(
        release.bump,
        ["minor", "--no-commit", "--no-tag"],
        catch_exceptions=False,
        input="y",
    )
    assert result.output.splitlines()[0].startswith("Running: bump-my-version bump")
    assert "Running: towncrier build --yes --version=14.0.0.2.0" in result.output
    assert "No repo to push" in result.output
    assert result.exit_code == 0


# TODO: test more cases
@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_push_repo_with_pending_merge(project):
    ran_cmd = []
    real_run = release.run

    def mocked_run(cmd, **kwargs):
        # Only the per-repo branch push runs with an explicit cwd; record those
        # and let the real bump/towncrier commands execute.
        if "cwd" in kwargs:
            ran_cmd.append(cmd)
            return ""
        return real_run(cmd, **kwargs)

    mock_pending_merge_repo_paths("edi-framework")
    # run init to get all files ready (eg: towncrier)
    project.invoke(init, catch_exceptions=False)
    with mock.patch("odoo_tools.cli.release.run", mocked_run):
        result = project.invoke(
            release.bump,
            ["minor", "--no-commit", "--no-tag"],
            catch_exceptions=False,
            input="y",
        )
    assert result.exit_code == 0
    assert ran_cmd == [
        "git config remote.camptocamp.url",
        "git push -f -v camptocamp HEAD:refs/heads/merge-branch-1234-14.0.0.2.0",
    ]
    # the pushed repo shows up in the live progress grid
    assert "edi-framework" in result.output


def test_get_new_release_notes(tmp_path):
    repo = git.Repo.init(tmp_path)
    with repo.config_writer() as cfg:
        cfg.set_value("user", "email", "test@test.com")
        cfg.set_value("user", "name", "Test")
    head = (
        ".. :changelog:\n"
        ".. DO NOT EDIT. File is generated from fragments.\n\n"
        "Release History\n"
        "---------------\n\n"
        ".. towncrier release notes start\n\n"
    )
    old = "14.0.0.1.0 (2011-10-09)\n+++++++++++++++++++++++\n\n* Blah\n"
    history = tmp_path / "HISTORY.rst"
    history.write_text(head + old)
    repo.git.add("-A")
    repo.git.commit("--message", "init")
    # towncrier inserts the new release block right after the marker
    new_block = (
        "14.0.0.2.0 (2026-06-29)\n"
        "+++++++++++++++++++++++\n\n"
        "**Features and Improvements**\n\n"
        "* 2345: Added a thing!\n\n"
        "**Bugfixes**\n\n"
        "* 1234: Fixed a thing!\n\n\n"
    )
    history.write_text(head + new_block + old)
    expected = (
        "**Features and Improvements**\n\n"
        "* 2345: Added a thing!\n\n"
        "**Bugfixes**\n\n"
        "* 1234: Fixed a thing!"
    )
    assert release.get_new_release_notes(repo, history) == expected


def test_tag_signing_enabled(tmp_path):
    repo = git.Repo.init(tmp_path)
    # tag.gpgsign is authoritative when set
    with repo.config_writer() as cfg:
        cfg.set_value("tag", "gpgsign", "true")
    assert tag_signing_enabled(repo) is True
    with repo.config_writer() as cfg:
        cfg.set_value("tag", "gpgsign", "false")
    assert tag_signing_enabled(repo) is False


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_commit_and_tag(project):
    project.invoke(init, catch_exceptions=False)
    cwd = Path()
    (cwd / "changes.d/1234.bug").write_text("Fixed a thing!")
    (cwd / "changes.d/2345.feat").write_text("Added a thing!")
    # the commit flow requires a clean tree to start from
    git_commit_all()
    result = project.invoke(
        release.bump,
        ["minor", "--commit", "--tag"],
        catch_exceptions=False,
        input="n",
    )
    assert result.exit_code == 0
    assert '✅ Committed "Release 14.0.0.2.0"' in result.output
    assert '✅ Created tag "14.0.0.2.0"' in result.output
    repo = git.Repo(".")
    # A "Release X" commit was created, and it includes the release files
    assert repo.head.commit.message.strip() == "Release 14.0.0.2.0"
    committed_files = repo.head.commit.stats.files
    assert "HISTORY.rst" in committed_files
    # The annotated tag exists and its message is the release notes without the title
    tag_object = repo.tags["14.0.0.2.0"].tag
    assert tag_object is not None
    message = tag_object.message
    assert "14.0.0.2.0 (" not in message
    assert "+++" not in message
    assert "**Features and Improvements**" in message
    assert "* 2345: Added a thing!" in message
    assert "**Bugfixes**" in message
    assert "* 1234: Fixed a thing!" in message
    # No manual commit/tag tips, since the tool did both
    assert "git commit -m" not in result.output
    assert "git tag -a" not in result.output
    # The working tree is clean afterwards
    assert not repo.is_dirty(untracked_files=True, submodules=False)


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_commit_no_tag(project):
    project.invoke(init, catch_exceptions=False)
    # the commit flow requires a clean tree to start from
    git_commit_all()
    result = project.invoke(
        release.bump,
        ["minor", "--commit", "--no-tag"],
        catch_exceptions=False,
        input="n",
    )
    assert result.exit_code == 0
    repo = git.Repo(".")
    # The commit was created but no tag
    assert repo.head.commit.message.strip() == "Release 14.0.0.2.0"
    assert len(repo.tags) == 0
    # Only the tag tip is shown (commit was done by the tool)
    assert "git commit -m" not in result.output
    assert "git tag -a 14.0.0.2.0" in result.output


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_tag_recreate(project):
    project.invoke(init, catch_exceptions=False)
    git_commit_all()
    repo = git.Repo(".")
    # Pre-create the tag the bump will want to create
    repo.create_tag("14.0.0.2.0", message="old message")
    # push? no / re-create tag? yes
    result = project.invoke(
        release.bump,
        ["minor", "--commit", "--tag"],
        catch_exceptions=False,
        input="n\ny\n",
    )
    assert result.exit_code == 0
    assert 'Tag "14.0.0.2.0" already exists. Re-create it?' in result.output
    # The tag was replaced: it now points at the release commit, not the old message
    tag = repo.tags["14.0.0.2.0"]
    tag_object = tag.tag
    assert tag_object is not None
    assert tag_object.message != "old message"
    assert tag.commit == repo.head.commit


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_tag_recreate_declined(project):
    project.invoke(init, catch_exceptions=False)
    git_commit_all()
    repo = git.Repo(".")
    repo.create_tag("14.0.0.2.0", message="old message")
    # push? no / re-create tag? no
    result = project.invoke(
        release.bump,
        ["minor", "--commit", "--tag"],
        catch_exceptions=False,
        input="n\nn\n",
    )
    assert result.exit_code == 0
    # The commit was still created, but the existing tag is left untouched
    assert repo.head.commit.message.strip() == "Release 14.0.0.2.0"
    tag_object = repo.tags["14.0.0.2.0"].tag
    assert tag_object is not None
    assert tag_object.message == "old message"
    assert "✅ Created tag" not in result.output


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_prompts_commit_and_tag(project):
    project.invoke(init, catch_exceptions=False)
    # the commit flow requires a clean tree to start from
    git_commit_all()
    # push? no / commit? yes / tag? yes  (prompts are asked in that order)
    result = project.invoke(
        release.bump, ["minor"], catch_exceptions=False, input="n\ny\ny\n"
    )
    assert result.exit_code == 0
    assert "Create the release commit?" in result.output
    assert "Create the release tag?" in result.output
    repo = git.Repo(".")
    assert repo.head.commit.message.strip() == "Release 14.0.0.2.0"
    assert "14.0.0.2.0" in [tag.name for tag in repo.tags]


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_prompts_decline_commit(project):
    project.invoke(init, catch_exceptions=False)
    # check(a) runs while the commit decision is undecided, so start clean
    git_commit_all()
    head_before = git.Repo(".").head.commit.hexsha
    # commit? no -> the tag prompt must NOT appear / push? no
    result = project.invoke(
        release.bump, ["minor"], catch_exceptions=False, input="n\nn\n"
    )
    assert result.exit_code == 0
    assert "Create the release commit?" in result.output
    assert "Create the release tag?" not in result.output
    repo = git.Repo(".")
    assert repo.head.commit.hexsha == head_before
    assert len(repo.tags) == 0


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_no_commit(project):
    project.invoke(init, catch_exceptions=False)
    head_before = git.Repo(".").head.commit.hexsha
    result = project.invoke(
        release.bump,
        ["minor", "--no-commit", "--no-tag"],
        catch_exceptions=False,
        input="n",
    )
    assert result.exit_code == 0
    repo = git.Repo(".")
    assert repo.head.commit.hexsha == head_before
    assert len(repo.tags) == 0
    # Manual commit and tag tips are shown since the tool did neither
    assert 'git commit -m "Release 14.0.0.2.0"' in result.output
    assert "git tag -a 14.0.0.2.0" in result.output


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_tag_requires_commit(project):
    project.invoke(init, catch_exceptions=False)
    ver_file = config.version_file_rel_path
    result = project.invoke(release.bump, ["minor", "--tag", "--no-commit"])
    assert result.exit_code != 0
    assert "--tag requires --commit" in result.output
    # Version untouched (we fail before mutating anything)
    assert ver_file.read_text() == "14.0.0.1.0"


@pytest.mark.project_setup(
    proj_version="14.0.0.1.0", mock_marabunta_file=True, git_init=True
)
def test_bump_fails_on_unstaged_changes(project):
    project.invoke(init, catch_exceptions=False)
    git_commit_all()
    # Modify a tracked file without staging it
    Path("requirements.txt").write_text("a-dependency\n")
    ver_file = config.version_file_rel_path
    result = project.invoke(release.bump, ["minor", "--commit"])
    assert result.exit_code != 0
    assert "uncommitted changes" in result.output.lower()
    # The release did not proceed
    assert ver_file.read_text() == "14.0.0.1.0"
