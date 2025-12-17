# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from pathlib import Path
from unittest import mock

import pytest

from odoo_tools.cli.project import checkout_local_odoo, init
from odoo_tools.utils.config import config
from odoo_tools.utils.path import build_path

from .common import compare_line_by_line, get_fixture, mock_subprocess_run


@pytest.mark.parametrize(
    ("version"),
    [
        pytest.param(
            1,
            marks=pytest.mark.project_setup(proj_tmpl_ver=1),
        ),
        pytest.param(
            2,
            marks=pytest.mark.project_setup(proj_tmpl_ver=2, proj_version="16.0.1.1.0"),
        ),
    ],
)
def test_init(project, version):
    # Drop mocked cfg (necessary to make fake_project_root work before)
    os.remove(".proj.cfg")
    config._reload()
    with mock.patch.dict(os.environ, {"PROJ_TMPL_VER": str(version)}, clear=True):
        result = project.invoke(init, catch_exceptions=False)
    paths = (
        ".proj.cfg",
        "docker-compose.override.yml",
        "changes.d/.gitkeep",
        "towncrier.toml",
        ".towncrier-template.rst",
        "HISTORY.rst",
    )
    for path in paths:
        assert os.path.exists(path), f"`{path}` missing"
    with open(".bumpversion.cfg") as fd:
        content = fd.read()
        expected = get_fixture(f"expected.bumpversion.v{version}.cfg")
        compare_line_by_line(content, expected)
    with open(".proj.cfg") as fd:
        content = fd.read()
        expected = get_fixture(f"expected.proj.v{version}.cfg")
        compare_line_by_line(content, expected)
    assert result.exit_code == 0
    autoshare_cache_dir = Path("./.cache/git-autoshare").absolute()
    autoshare_config_dir = Path("./.config/git-autoshare").absolute()
    os.environ["GIT_AUTOSHARE_CACHE_DIR"] = str(autoshare_cache_dir)
    os.environ["GIT_AUTOSHARE_CONFIG_DIR"] = str(autoshare_config_dir)


@pytest.mark.project_setup(proj_tmpl_ver=1)
def test_init_proj_conf_already_existing(project):
    orig_content = get_fixture("expected.proj.v1.cfg")
    expected = orig_content + "\nfoo = baz"
    with open(".proj.cfg", "w") as fd:
        fd.write(expected)
    with open("docker-compose.override.yml", "w") as fd:
        fd.write("version: '9.7'\nservices:\n  odoo:\n    image: odoo:16.0\n")
    result = project.invoke(init, catch_exceptions=False)
    with open(".proj.cfg") as fd:
        content = fd.read()
        # original cfg has been preserved
        assert content == expected
    assert build_path("docker-compose.override.yml.bak").exists()
    assert result.exit_code == 0


@pytest.mark.project_setup(
    proj_tmpl_ver=1,
    extra_files={"HISTORY.rst": get_fixture("fake-deprecated-history.rst")},
)
def test_init_history_file_already_existing(project):
    result = project.invoke(init, catch_exceptions=False)
    assert (
        build_path("changes.d/BS-31.feat").read_text()
        == "Install the ``module_a`` and ``module_b`` modules\n"
    )
    assert (
        build_path("changes.d/BS-32.feat").read_text()
        == "Install the ``module_c`` module\n"
    )
    assert build_path("changes.d/BS-42.bug").read_text() == "Uninstall ``module_d``\n"
    assert not build_path("changes.d/BS-12.feat").exists()
    assert build_path("HISTORY.rst").read_text() == get_fixture(
        "fake-converted-history.rst"
    )
    assert result.exit_code == 0


@pytest.mark.project_setup(
    proj_tmpl_ver=1,
    extra_files={"HISTORY.rst": get_fixture("fake-converted-history.rst")},
)
def test_init_history_file_already_existing_but_already_converted(project):
    result = project.invoke(init, catch_exceptions=False)
    assert not build_path("changes.d/BS-31.feat").exists()
    assert not build_path("changes.d/BS-32.feat").exists()
    assert not build_path("changes.d/BS-42.bug").exists()
    assert not build_path("changes.d/BS-12.feat").exists()
    assert build_path("HISTORY.rst").read_text() == get_fixture(
        "fake-converted-history.rst"
    )
    assert result.exit_code == 0


@pytest.mark.project_setup(proj_tmpl_ver=2)
def test_init_custom_version(project):
    result = project.invoke(
        init,
        [
            "--version",
            "16.0.1.1.0",
        ],
        catch_exceptions=False,
    )
    assert os.path.exists("docker-compose.override.yml")
    with open(".bumpversion.cfg") as fd:
        content = fd.read()
        expected = get_fixture("expected.bumpversion.v2.cfg")
        compare_line_by_line(content, expected)
    assert result.exit_code == 0


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=2, proj_version="16.0.1.1.0")
def test_checkout_local_odoo(runner):
    odoo_src_path = build_path(config.odoo_src_rel_path)
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "git",
                    "clone",
                    "--quiet",
                    "--no-checkout",
                    "git@github.com:odoo/odoo",
                    str(odoo_src_path / "odoo"),
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "-C",
                    str(odoo_src_path / "odoo"),
                    "fetch",
                    "--quiet",
                    "origin",
                    "12345",
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "-C",
                    str(odoo_src_path / "odoo"),
                    "checkout",
                    "--force",
                    "12345",
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "clone",
                    "--quiet",
                    "--no-checkout",
                    "git@github.com:odoo/enterprise",
                    str(odoo_src_path / "enterprise"),
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "-C",
                    str(odoo_src_path / "enterprise"),
                    "fetch",
                    "--quiet",
                    "origin",
                    "56789",
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "-C",
                    str(odoo_src_path / "enterprise"),
                    "checkout",
                    "--force",
                    "56789",
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
        ]
    )
    with mock.patch("subprocess.run", mock_fn):
        runner.invoke(
            checkout_local_odoo,
            ["--odoo-hash", "12345", "--enterprise-hash", "56789"],
            catch_exceptions=False,
        )


@pytest.mark.usefixtures("project")
@pytest.mark.project_setup(proj_tmpl_ver=2, proj_version="16.0.1.1.0")
def test_local_odoo_venv(runner):
    odoo_src_path = build_path(config.odoo_src_rel_path)
    config_file = build_path("odoo.cfg")

    def create_config():
        with open(config_file, "w") as fobj:
            fobj.write("db_name=testdb\n")

    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "git",
                    "clone",
                    "--quiet",
                    "--no-checkout",
                    "git@github.com:odoo/odoo",
                    str(odoo_src_path / "odoo"),
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "-C",
                    str(odoo_src_path / "odoo"),
                    "fetch",
                    "--quiet",
                    "origin",
                    "12345",
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "-C",
                    str(odoo_src_path / "odoo"),
                    "checkout",
                    "--force",
                    "12345",
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "clone",
                    "--quiet",
                    "--no-checkout",
                    "git@github.com:odoo/enterprise",
                    str(odoo_src_path / "enterprise"),
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "-C",
                    str(odoo_src_path / "enterprise"),
                    "fetch",
                    "--quiet",
                    "origin",
                    "56789",
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": [
                    "git",
                    "-C",
                    str(odoo_src_path / "enterprise"),
                    "checkout",
                    "--force",
                    "56789",
                ],
                # "sim_call": sim_touch,
                # "sim_call_args": ["foo"],
            },
            {
                "args": lambda a: Path(a[0]).name.startswith("python")
                and a[2] == "ensurepip",
            },
            {
                "args": lambda a: str(a[0]).endswith("pip")
                and str(a[3]).endswith(f"{odoo_src_path}/requirements.txt"),
            },
            {
                "args": lambda a: str(a[0]).endswith("pip")
                and a[1:] == ["install", "-r", "local-requirements.txt"]
            },
            {
                "args": lambda a: str(a[0]).endswith("pip")
                and str(a[3]).endswith("/requirements.txt")
            },
            {
                "args": lambda a: str(a[0]).endswith("pip")
                and a[1:] == ["install", "-e", "."]
            },
            {
                "args": None,
                "sim_call": create_config,
            },  # odoo config file generation, tested elsewhere
        ]
    )
    with mock.patch("subprocess.run", mock_fn):
        runner.invoke(
            checkout_local_odoo,
            [
                "--odoo-hash",
                "12345",
                "--enterprise-hash",
                "56789",
                "--venv",
            ],
            catch_exceptions=False,
        )
