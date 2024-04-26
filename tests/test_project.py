# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from unittest import mock

from odoo_tools.cli.project import checkout_local_odoo, init
from odoo_tools.config import get_conf_key
from odoo_tools.utils.path import build_path

from .common import (
    compare_line_by_line,
    fake_project_root,
    get_fixture,
    mock_subprocess_run,
)
from .fixtures import clear_caches  # noqa


@mock.patch.dict(os.environ, {"PROJ_TMPL_VER": "2"}, clear=True)
def test_init():
    with fake_project_root(proj_tmpl_ver="2", proj_version="16.0.1.1.0") as runner:
        # Drop mocked cfg (necessary to make fake_project_root work before)
        os.remove(".proj.cfg")
        result = runner.invoke(init, catch_exceptions=False)
        paths = (
            ".proj.cfg",
            "docker-compose.override.yml",
            "changes.d/.gitkeep",
            "towncrier.toml",
            ".towncrier-template.rst",
        )
        for path in paths:
            assert os.path.exists(path), f"`{path}` missing"
        with open(".bumpversion.cfg") as fd:
            content = fd.read()
            expected = get_fixture("expected.bumpversion.v2.cfg")
            compare_line_by_line(content, expected)
        with open(".proj.cfg") as fd:
            content = fd.read()
            expected = get_fixture("expected.proj.v2.cfg")
            compare_line_by_line(content, expected)
        assert result.exit_code == 0


@mock.patch.dict(os.environ, {"PROJ_TMPL_VER": "1"}, clear=True)
def test_init_v1():
    with fake_project_root() as runner:
        os.remove(".proj.cfg")
        result = runner.invoke(init, catch_exceptions=False)
        paths = (
            ".proj.cfg",
            "docker-compose.override.yml",
            "changes.d/.gitkeep",
            "towncrier.toml",
            ".towncrier-template.rst",
        )
        for path in paths:
            assert os.path.exists(path), f"`{path}` missing"
        with open(".bumpversion.cfg") as fd:
            content = fd.read()
            expected = get_fixture("expected.bumpversion.cfg")
            compare_line_by_line(content, expected)
        with open(".proj.cfg") as fd:
            content = fd.read()
            expected = get_fixture("expected.proj.v1.cfg")
            compare_line_by_line(content, expected, sort=True)
        assert result.exit_code == 0


def test_init_proj_conf_already_existing():
    with fake_project_root() as runner:
        orig_content = get_fixture("expected.proj.v1.cfg")
        expected = orig_content + "\nfoo = baz"
        with open(".proj.cfg", "w") as fd:
            fd.write(expected)
        result = runner.invoke(init, catch_exceptions=False)
        with open(".proj.cfg") as fd:
            content = fd.read()
            # original cfg has been preserved
            assert content == expected
        assert result.exit_code == 0


def test_init_custom_version():
    with fake_project_root(proj_tmpl_ver="2") as runner:
        result = runner.invoke(
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


def test_checkout_local_odoo():
    with fake_project_root(proj_tmpl_ver="2", proj_version="16.0.1.1.0") as runner:
        odoo_src_path = str(build_path(get_conf_key("odoo_src_rel_path")))
        odoo_enterprise_path = str(os.path.join(odoo_src_path, "..", "enterprise"))
        mock_fn = mock_subprocess_run(
            [
                {
                    "args": [
                        "git",
                        "clone",
                        "--quiet",
                        "--branch",
                        "16.0",
                        "git@github.com:odoo/odoo",
                        odoo_src_path,
                    ],
                    # "sim_call": sim_touch,
                    # "sim_call_args": ["foo"],
                },
                {
                    "args": [
                        "git",
                        "-C",
                        odoo_src_path,
                        "checkout",
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
                        "--branch",
                        "16.0",
                        "git@github.com:odoo/enterprise",
                        odoo_enterprise_path,
                    ],
                    # "sim_call": sim_touch,
                    # "sim_call_args": ["foo"],
                },
                {
                    "args": [
                        "git",
                        "-C",
                        odoo_enterprise_path,
                        "checkout",
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


def test_local_odoo_venv():
    with fake_project_root(proj_tmpl_ver="2", proj_version="16.0.1.1.0") as runner:
        odoo_src_path = str(build_path(get_conf_key("odoo_src_rel_path")))
        odoo_enterprise_path = str(os.path.join(odoo_src_path, "..", "enterprise"))
        config_file = build_path("odoo.cfg")

        def create_config():
            with open(config_file, "w") as fobj:
                fobj.write('db_name=testdb\n')

        mock_fn = mock_subprocess_run(
            [
                {
                    "args": [
                        "git",
                        "clone",
                        "--quiet",
                        "--branch",
                        "16.0",
                        "git@github.com:odoo/odoo",
                        odoo_src_path,
                    ],
                    # "sim_call": sim_touch,
                    # "sim_call_args": ["foo"],
                },
                {
                    "args": [
                        "git",
                        "-C",
                        odoo_src_path,
                        "checkout",
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
                        "--branch",
                        "16.0",
                        "git@github.com:odoo/enterprise",
                        odoo_enterprise_path,
                    ],
                    # "sim_call": sim_touch,
                    # "sim_call_args": ["foo"],
                },
                {
                    "args": [
                        "git",
                        "-C",
                        odoo_enterprise_path,
                        "checkout",
                        "56789",
                    ],
                    # "sim_call": sim_touch,
                    # "sim_call_args": ["foo"],
                },
                {
                    "args": lambda a: str(a[0]).endswith('python')
                    and a[2] == "ensurepip",
                },
                {
                    "args": lambda a: str(a[0]).endswith('pip')
                    and str(a[3]).endswith("odoo/src/requirements.txt"),
                },
                {
                    "args": lambda a: str(a[0]).endswith('pip')
                    and a[1:] == ["install", "-r", "local-requirements.txt"]
                },
                {
                    "args": lambda a: str(a[0]).endswith('pip')
                    and str(a[3]).endswith("/requirements.txt")
                },
                {
                    "args": lambda a: str(a[0]).endswith('pip')
                    and a[1:] == ['install', '-e', '.']
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
                    '--venv',
                ],
                catch_exceptions=False,
            )
