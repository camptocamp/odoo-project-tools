# Copyright 2024 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import pytest
from click.testing import CliRunner

from odoo_tools.utils.proj import get_project_manifest

from .common import make_fake_project_root


@pytest.fixture()
def runner():
    """Fixture to create a Click runner."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        yield runner


@pytest.fixture()
def project(request, runner):
    """Fixture to create a fake project root.

    The options can be passed as a marker on the test function:

    .. code-block:: python

        @pytest.mark.project_setup(
            manifest=dict(odoo_version="16.0"),
            proj_version="16.0.1.1.0",
        )
        def test_something(project):
            pass
    """
    kwargs = {}
    for marker in reversed(list(request.node.iter_markers("project_setup"))):
        kwargs.update(marker.kwargs)
    make_fake_project_root(**kwargs)
    return runner


@pytest.fixture(autouse=True)
def clear_caches():
    get_project_manifest.cache_clear()
