# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path

from odoo_tools.utils.completion import (
    SHELLS,
    completion_file_name,
    generate_completion_files,
    read_project_scripts,
)


def test_read_project_scripts_contains_otools_commands():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    scripts = read_project_scripts(pyproject)
    assert "otools-project" in scripts
    assert "otools-password" in scripts
    assert "otools-setup" in scripts
    assert len(scripts) == 13


def test_generate_completion_files_for_all_scripts(tmp_path):
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    scripts = read_project_scripts(pyproject)

    written = generate_completion_files(scripts, tmp_path)

    assert len(written) == len(scripts) * len(SHELLS)

    for prog_name in scripts:
        bash_file = tmp_path / "bash" / completion_file_name(prog_name, "bash")
        zsh_file = tmp_path / "zsh" / completion_file_name(prog_name, "zsh")
        fish_file = tmp_path / "fish" / completion_file_name(prog_name, "fish")

        assert bash_file.exists()
        assert zsh_file.exists()
        assert fish_file.exists()

        complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"

        bash_content = bash_file.read_text()
        zsh_content = zsh_file.read_text()
        fish_content = fish_file.read_text()

        assert complete_var in bash_content
        assert complete_var in zsh_content
        assert complete_var in fish_content

        assert prog_name in bash_content
        assert prog_name in zsh_content
        assert prog_name in fish_content
