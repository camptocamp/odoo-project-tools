# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""Tests for otools-setup and the completion setup helpers."""

from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from odoo_tools.cli.setup import cli
from odoo_tools.utils.completion import (
    BLOCK_BEGIN,
    BLOCK_END,
    build_completion_block,
    detect_shell,
    diff_rc_content,
    installed_completions_dir,
    shell_rc_file,
    update_rc_content,
)

# ---------------------------------------------------------------------------
# detect_shell
# ---------------------------------------------------------------------------


def test_detect_shell_bash():
    with mock.patch.dict("os.environ", {"SHELL": "/bin/bash"}):
        assert detect_shell() == "bash"


def test_detect_shell_zsh():
    with mock.patch.dict("os.environ", {"SHELL": "/usr/bin/zsh"}):
        assert detect_shell() == "zsh"


def test_detect_shell_fish():
    with mock.patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
        assert detect_shell() == "fish"


def test_detect_shell_unknown():
    with mock.patch.dict("os.environ", {"SHELL": "/bin/sh"}):
        assert detect_shell() is None


def test_detect_shell_missing():
    env = {k: v for k, v in __import__("os").environ.items() if k != "SHELL"}
    with mock.patch.dict("os.environ", env, clear=True):
        assert detect_shell() is None


# ---------------------------------------------------------------------------
# shell_rc_file
# ---------------------------------------------------------------------------


def test_shell_rc_file_bash():
    path = shell_rc_file("bash")
    assert path is not None
    assert path.name == ".bashrc"


def test_shell_rc_file_zsh():
    path = shell_rc_file("zsh")
    assert path is not None
    assert path.name == ".zshrc"


def test_shell_rc_file_fish_is_none():
    """Fish does not use an RC-file for completion; should return None."""
    assert shell_rc_file("fish") is None


# ---------------------------------------------------------------------------
# build_completion_block
# ---------------------------------------------------------------------------


def test_build_completion_block_bash_contains_markers(tmp_path):
    block = build_completion_block("bash", tmp_path / "completions")
    assert BLOCK_BEGIN in block
    assert BLOCK_END in block


def test_build_completion_block_bash_snippet(tmp_path):
    completions_dir = tmp_path / "completions"
    block = build_completion_block("bash", completions_dir)
    assert str(completions_dir) in block
    assert "source" in block


def test_build_completion_block_zsh_snippet(tmp_path):
    completions_dir = tmp_path / "completions"
    block = build_completion_block("zsh", completions_dir)
    assert str(completions_dir) in block
    assert "fpath" in block
    assert "compinit" in block


def test_build_completion_block_unsupported_shell(tmp_path):
    with pytest.raises(ValueError, match="unsupported shell"):
        build_completion_block("fish", tmp_path)


# ---------------------------------------------------------------------------
# update_rc_content — append when block missing
# ---------------------------------------------------------------------------


def test_update_rc_content_appends_block(tmp_path):
    existing = "# existing content\nexport FOO=bar\n"
    updated = update_rc_content(existing, "bash", tmp_path / "completions")
    assert BLOCK_BEGIN in updated
    assert BLOCK_END in updated
    # Original content preserved
    assert "# existing content" in updated


def test_update_rc_content_append_has_separator(tmp_path):
    existing = "export FOO=bar\n"
    updated = update_rc_content(existing, "bash", tmp_path / "completions")
    # Block must not be glued directly to existing content without a newline
    idx_end = updated.rfind("export FOO=bar")
    idx_begin = updated.find(BLOCK_BEGIN)
    between = updated[idx_end + len("export FOO=bar") : idx_begin]
    assert "\n" in between


# ---------------------------------------------------------------------------
# update_rc_content — idempotency
# ---------------------------------------------------------------------------


def test_update_rc_content_idempotent(tmp_path):
    completions_dir = tmp_path / "completions"
    existing = "export FOO=bar\n"
    first = update_rc_content(existing, "bash", completions_dir)
    second = update_rc_content(first, "bash", completions_dir)
    assert first == second


def test_update_rc_content_replaces_existing_block(tmp_path):
    old_dir = tmp_path / "old_completions"
    new_dir = tmp_path / "new_completions"
    existing = "export FOO=bar\n" + build_completion_block("bash", old_dir) + "\n"
    updated = update_rc_content(existing, "bash", new_dir)
    assert str(new_dir) in updated
    assert str(old_dir) not in updated
    # Only one block present
    assert updated.count(BLOCK_BEGIN) == 1


# ---------------------------------------------------------------------------
# diff_rc_content
# ---------------------------------------------------------------------------


def test_diff_rc_content_shows_diff(tmp_path):
    rc = tmp_path / ".bashrc"
    original = "# existing\n"
    updated = original + build_completion_block("bash", tmp_path / "completions") + "\n"
    diff = diff_rc_content(original, updated, rc)
    assert diff  # non-empty
    assert BLOCK_BEGIN in diff


def test_diff_rc_content_empty_when_no_change(tmp_path):
    rc = tmp_path / ".bashrc"
    content = "# no changes\n"
    diff = diff_rc_content(content, content, rc)
    assert diff == ""


# ---------------------------------------------------------------------------
# installed_completions_dir
# ---------------------------------------------------------------------------


def test_installed_completions_dir_is_path():
    path = installed_completions_dir()
    assert isinstance(path, Path)


def test_installed_completions_dir_contains_bash():
    path = installed_completions_dir()
    # The bash subdirectory must exist in a properly installed package
    bash_dir = path / "bash"
    assert bash_dir.exists(), f"Expected bash completion dir at {bash_dir}"


# ---------------------------------------------------------------------------
# CLI — shell-completion command (bash)
# ---------------------------------------------------------------------------


def test_cli_shell_completion_bash_preview_and_approve(tmp_path, monkeypatch):
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text("# existing\n")
    completions_dir = installed_completions_dir()

    monkeypatch.setattr(
        "odoo_tools.cli.setup.installed_completions_dir", lambda: completions_dir
    )
    monkeypatch.setattr("odoo_tools.cli.setup.shell_rc_file", lambda shell: rc_file)

    runner = CliRunner()
    result = runner.invoke(cli, ["shell-completion", "--shell", "bash"], input="y\n")
    assert result.exit_code == 0, result.output
    content = rc_file.read_text()
    assert BLOCK_BEGIN in content
    assert BLOCK_END in content


def test_cli_shell_completion_bash_abort(tmp_path, monkeypatch):
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text("# existing\n")

    monkeypatch.setattr(
        "odoo_tools.cli.setup.installed_completions_dir",
        lambda: tmp_path / "completions",
    )
    monkeypatch.setattr("odoo_tools.cli.setup.shell_rc_file", lambda shell: rc_file)

    runner = CliRunner()
    result = runner.invoke(cli, ["shell-completion", "--shell", "bash"], input="n\n")
    # Abort exits with non-zero
    assert result.exit_code != 0
    # RC file must be unchanged
    assert rc_file.read_text() == "# existing\n"


def test_cli_shell_completion_no_op_when_already_configured(tmp_path, monkeypatch):
    completions_dir = installed_completions_dir()
    existing = build_completion_block("bash", completions_dir) + "\n"
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text(existing)

    monkeypatch.setattr(
        "odoo_tools.cli.setup.installed_completions_dir", lambda: completions_dir
    )
    monkeypatch.setattr("odoo_tools.cli.setup.shell_rc_file", lambda shell: rc_file)

    runner = CliRunner()
    result = runner.invoke(cli, ["shell-completion", "--shell", "bash"])
    assert result.exit_code == 0
    assert "already up to date" in result.output


def test_cli_shell_completion_unknown_shell_env_error(monkeypatch):
    monkeypatch.delenv("SHELL", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["shell-completion"])
    assert result.exit_code != 0
    assert "Could not detect" in result.output or "Error" in result.output


# ---------------------------------------------------------------------------
# CLI — shell-completion command (fish)
# ---------------------------------------------------------------------------


def test_cli_shell_completion_fish_copies_files(tmp_path, monkeypatch):
    completions_dir = installed_completions_dir()
    fish_target = tmp_path / "fish" / "completions"

    monkeypatch.setattr(
        "odoo_tools.cli.setup.installed_completions_dir", lambda: completions_dir
    )
    monkeypatch.setattr(
        "odoo_tools.cli.setup.fish_completions_dir", lambda: fish_target
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["shell-completion", "--shell", "fish"], input="y\n")
    assert result.exit_code == 0, result.output
    assert fish_target.exists()
    fish_files = list(fish_target.glob("*.fish"))
    assert fish_files, "Expected fish completion files to be copied"


def test_cli_shell_completion_fish_abort(tmp_path, monkeypatch):
    completions_dir = installed_completions_dir()
    fish_target = tmp_path / "fish" / "completions"

    monkeypatch.setattr(
        "odoo_tools.cli.setup.installed_completions_dir", lambda: completions_dir
    )
    monkeypatch.setattr(
        "odoo_tools.cli.setup.fish_completions_dir", lambda: fish_target
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["shell-completion", "--shell", "fish"], input="n\n")
    assert result.exit_code != 0
    assert not fish_target.exists() or not list(fish_target.glob("*.fish"))
