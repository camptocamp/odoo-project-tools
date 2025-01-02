from pathlib import Path
from unittest import mock

import pytest

from odoo_tools.cli import submodule

from .common import get_fixture_path, mock_subprocess_run


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_init(project):
    odoo_version = "16.0"
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "git",
                    "autoshare-submodule-add",
                    "-b",
                    odoo_version,
                    "--force",
                    "git@github.com:OCA/account-closing.git",
                    "odoo/external-src/account-closing",
                ],
            },
            {
                "args": [
                    "git",
                    "autoshare-submodule-add",
                    "-b",
                    odoo_version,
                    "--force",
                    "git@github.com:OCA/account-financial-reporting.git",
                    "odoo/external-src/account-financial-reporting",
                ],
            },
        ]
    )
    with mock.patch("subprocess.run", mock_fn):
        result = project.invoke(
            submodule.init,
            [],
            catch_exceptions=False,
        )
    mock_fn.assert_completed_calls()
    assert result.exit_code == 0


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
)
def test_init_missing_gitmodules(project):
    mock_fn = mock_subprocess_run([])
    with mock.patch("subprocess.run", mock_fn):
        result = project.invoke(
            submodule.init,
            [],
            catch_exceptions=False,
        )
    mock_fn.assert_completed_calls()
    assert result.exit_code == 0


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_update(project):
    mock_fn = mock_subprocess_run(
        [
            {
                "args": [
                    "git",
                    "submodule",
                    "sync",
                    "--",
                    "odoo/external-src/account-closing",
                ],
            },
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "odoo/external-src/account-closing",
                ],
            },
            {
                "args": [
                    "git",
                    "submodule",
                    "sync",
                    "--",
                    "odoo/external-src/account-financial-reporting",
                ],
            },
            {
                "args": [
                    "git",
                    "submodule",
                    "update",
                    "--init",
                    "odoo/external-src/account-financial-reporting",
                ],
            },
        ]
    )
    with (
        mock.patch("subprocess.run", mock_fn),
        mock.patch(
            "odoo_tools.utils.git.find_autoshare_repository", return_value=(None, None)
        ),
    ):
        result = project.invoke(
            submodule.update,
            [],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_fn.assert_completed_calls()


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_ls(project):
    result = project.invoke(
        submodule.ls,
        ["--no-dockerfile"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "odoo/external-src/account-closing",
        "odoo/external-src/account-financial-reporting",
    ]


@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.2.3",
    extra_files={
        ".gitmodules": Path(get_fixture_path("fake-gitmodules")).read_text(),
    },
)
def test_ls_dockerfile(project):
    result = project.invoke(
        submodule.ls,
        ["--dockerfile"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        'ENV ADDONS_PATH="/odoo/odoo/external-src/account-closing, \\',
        "/odoo/odoo/external-src/account-financial-reporting, \\",
        "/odoo/src/odoo/odoo/addons, \\",
        "/odoo/src/odoo/addons, \\",
        "/odoo/enterprise, \\",
        '/odoo/odoo/addons" \\',
        "",
    ]
