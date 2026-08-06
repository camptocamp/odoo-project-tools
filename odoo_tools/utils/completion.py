# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import annotations

import io
import os
import re
from contextlib import redirect_stdout
from importlib import import_module
from importlib.resources import files
from pathlib import Path

SHELLS = ("bash", "zsh", "fish")


def read_project_scripts(pyproject_path: Path) -> dict[str, str]:
    """Read [project.scripts] from pyproject.toml without extra deps."""
    content = pyproject_path.read_text()
    in_scripts = False
    scripts: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and stripped.startswith("["):
            break
        if not in_scripts or not stripped or stripped.startswith("#"):
            continue
        match = re.match(r'([A-Za-z0-9_-]+)\s*=\s*"([^"]+)"', stripped)
        if match:
            scripts[match.group(1)] = match.group(2)
    if not scripts:
        raise RuntimeError("No [project.scripts] entry found in pyproject.toml")
    return scripts


def _load_click_command(import_path: str):
    module_name, attr_name = import_path.rsplit(":", 1)
    module = import_module(module_name)
    command = getattr(module, attr_name)
    return command


def _complete_var_name(prog_name: str) -> str:
    return f"_{prog_name.replace('-', '_').upper()}_COMPLETE"


def _render_shell_source(prog_name: str, import_path: str, shell: str) -> str:
    command = _load_click_command(import_path)
    complete_var = _complete_var_name(prog_name)
    stdout_buffer = io.BytesIO()
    stdout = io.TextIOWrapper(stdout_buffer, encoding="utf-8")
    previous = os.environ.get(complete_var)
    previous_skip_update = os.environ.get("OTOOLS_SKIP_UPDATE_CHECK")
    with redirect_stdout(stdout):
        os.environ[complete_var] = f"{shell}_source"
        os.environ["OTOOLS_SKIP_UPDATE_CHECK"] = "1"
        try:
            try:
                command.main(args=[], prog_name=prog_name, standalone_mode=False)
            except SystemExit as exc:
                if exc.code not in (0, None):
                    raise
        finally:
            if previous is None:
                os.environ.pop(complete_var, None)
            else:
                os.environ[complete_var] = previous
            if previous_skip_update is None:
                os.environ.pop("OTOOLS_SKIP_UPDATE_CHECK", None)
            else:
                os.environ["OTOOLS_SKIP_UPDATE_CHECK"] = previous_skip_update
    stdout.flush()
    source = stdout_buffer.getvalue().decode("utf-8")
    if not source.strip():
        raise RuntimeError(f"Empty completion source for {prog_name} ({shell})")
    return source


def completion_file_name(prog_name: str, shell: str) -> str:
    if shell == "bash":
        return prog_name
    if shell == "zsh":
        return f"_{prog_name}"
    if shell == "fish":
        return f"{prog_name}.fish"
    raise ValueError(f"Unsupported shell: {shell}")


def generate_completion_files(
    scripts: dict[str, str],
    output_dir: Path,
    shells: tuple[str, ...] = SHELLS,
) -> list[Path]:
    written: list[Path] = []
    for shell in shells:
        shell_dir = output_dir / shell
        shell_dir.mkdir(parents=True, exist_ok=True)
        for prog_name, import_path in sorted(scripts.items()):
            file_path = shell_dir / completion_file_name(prog_name, shell)
            source = _render_shell_source(prog_name, import_path, shell)
            if not source.endswith("\n"):
                source += "\n"
            file_path.write_text(source)
            written.append(file_path)
    return written


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def completion_output_dir(root: Path) -> Path:
    return root / "odoo_tools" / "completions"


def main() -> int:
    root = project_root()
    scripts = read_project_scripts(root / "pyproject.toml")
    written = generate_completion_files(scripts, completion_output_dir(root))
    print(f"Generated {len(written)} completion files.")
    return 0


# ---------------------------------------------------------------------------
# Shell setup helpers (used by otools-setup)
# ---------------------------------------------------------------------------

BLOCK_BEGIN = "# BEGIN otools-setup"
BLOCK_END = "# END otools-setup"

#: Supported shells and their default RC file (None = fish, handled separately)
SHELL_RC_FILES: dict[str, str] = {
    "bash": "~/.bashrc",
    "zsh": "~/.zshrc",
}


def installed_completions_dir() -> Path:
    """Return the Path of the installed package-data completion directory."""
    return Path(str(files("odoo_tools.completions")))


def detect_shell() -> str | None:
    """Return the name of the current shell (bash/zsh/fish) or None."""
    shell_env = os.environ.get("SHELL", "")
    name = Path(shell_env).name.lower()
    if name in SHELLS:
        return name
    return None


def shell_rc_file(shell: str) -> Path | None:
    """Return the Path to the shell startup file, or None for fish (no RC needed)."""
    rc = SHELL_RC_FILES.get(shell)
    if rc is None:
        return None
    return Path(rc).expanduser()


def build_completion_block(shell: str, completions_dir: Path) -> str:
    """Build the marked completion block to insert into a shell RC file.

    Returns the full block text including surrounding blank lines but *without*
    a trailing newline — callers decide how to join it.
    """
    dir_str = str(completions_dir)
    if shell == "bash":
        snippet = (
            f'OTOOLS_COMPLETIONS_DIR="{dir_str}"\n'
            'for f in "$OTOOLS_COMPLETIONS_DIR"/bash/*; do\n'
            "  # shellcheck disable=SC1090\n"
            '  source "$f"\n'
            "done"
        )
    elif shell == "zsh":
        snippet = f'fpath=("{dir_str}/zsh" $fpath)\nautoload -Uz compinit\ncompinit'
    else:
        raise ValueError(f"build_completion_block: unsupported shell {shell!r}")
    return f"{BLOCK_BEGIN}\n{snippet}\n{BLOCK_END}"


def fish_completions_dir() -> Path:
    """Return the default fish completions directory."""
    return Path("~/.config/fish/completions").expanduser()


def update_rc_content(existing_content: str, shell: str, completions_dir: Path) -> str:
    """Return the new RC-file content with the otools block inserted or replaced.

    If a marked block already exists it is replaced in-place.  Otherwise the
    block is appended at the end, separated by a blank line.
    """
    block = build_completion_block(shell, completions_dir)
    pattern = re.compile(
        rf"^{re.escape(BLOCK_BEGIN)}.*?^{re.escape(BLOCK_END)}",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(existing_content):
        return pattern.sub(block, existing_content)
    # Append with a leading blank line if the file doesn't already end with one.
    separator = "" if existing_content.endswith("\n\n") else "\n"
    if not existing_content.endswith("\n"):
        separator = "\n" + separator
    return existing_content + separator + block + "\n"


def diff_rc_content(original: str, updated: str, rc_path: Path) -> str:
    """Return a unified-diff-style string showing the proposed RC-file change."""
    import difflib

    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=str(rc_path),
        tofile=str(rc_path),
    )
    return "".join(diff)


if __name__ == "__main__":
    raise SystemExit(main())
