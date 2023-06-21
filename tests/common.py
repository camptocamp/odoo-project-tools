# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from contextlib import contextmanager
from pathlib import PosixPath

from click.testing import CliRunner

from odoo_tools.utils.path import get_root_marker
from odoo_tools.utils.yaml import update_yml_file

FIXTURES_PATH = PosixPath(__file__).parent / "fixtures"


def get_fixture_path(fname):
    return FIXTURES_PATH / fname


def get_fixture(fname):
    with open(get_fixture_path(fname)) as fd:
        return fd.read()


def mock_pypi_version_cache(pkg_name, version):
    """Hijack temporary cache to avoid mocking requests every time."""
    from odoo_tools.utils.pypi import TMP_CACHE

    TMP_CACHE[pkg_name] = version


FAKE_MANIFEST_DATA = dict(
    customer_name="ACME Inc.",
    odoo_version="14.0",
    customer_shortname="acme",
    repo_name="acme_odoo",
    project_id="1234",
    project_name="acme_odoo",
    odoo_company_name="ACME Inc.",
    country="ch",
    odoo_main_lang="de_DE",
    odoo_aux_langs="fr_CH;it_IT",
    platform_name="azure",
)


def make_fake_project_root(
    manifest=None, marker_file=get_root_marker(), req_file="requirements.txt"
):
    data = FAKE_MANIFEST_DATA.copy()
    data.update(manifest or {})
    # create empty file
    with open(marker_file, "w") as fd:
        fd.write("")
    # write YAML
    update_yml_file(marker_file, data)
    with open(req_file, "w") as fd:
        fd.write("")


@contextmanager
def fake_project_root(make_root=True, manifest=None):
    runner = CliRunner()
    # TODO: do we really need this click util
    # or tmpfile api is enough?
    with runner.isolated_filesystem():
        if make_root:
            make_fake_project_root(manifest=manifest)
        yield runner
