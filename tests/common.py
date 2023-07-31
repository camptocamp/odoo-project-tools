# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import os
from contextlib import contextmanager
from pathlib import PosixPath

from click.testing import CliRunner

from odoo_tools.config import get_conf_key
from odoo_tools.utils import pending_merge as pm_utils
from odoo_tools.utils.path import get_root_marker
from odoo_tools.utils.yaml import update_yml_file

Repo = pm_utils.Repo

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
FAKE_PROJ_CFG_V1 = dict(
    company_git_remote="camptocamp",
    odoo_src_rel_path="odoo/src",
    ext_src_rel_path="odoo/external-src",
    local_src_rel_path="odoo/local-src",
    pending_merge_rel_path="pending-merges.d",
    version_file_rel_path="odoo/VERSION",
    marabunta_mig_file_rel_path="odoo/migration.yml",
)
FAKE_PROJ_CFG_V2 = dict(
    company_git_remote="camptocamp",
    odoo_src_rel_path="odoo/src",
    ext_src_rel_path="odoo/external-src",
    local_src_rel_path="odoo/addons",
    pending_merge_rel_path="pending-merges.d",
    version_file_rel_path="VERSION",
    marabunta_mig_file_rel_path="migration.yml",
)
FAKE_PROJ_CFG_BY_VER = {"1": FAKE_PROJ_CFG_V1, "2": FAKE_PROJ_CFG_V2}


def make_fake_project_root(
    proj_tmpl_ver="1",
    proj_cfg=None,
    manifest=None,
    marker_file=get_root_marker(),
    req_file="requirements.txt",
    proj_version="14.0.0.1.0",
    mock_marabunta_file=False,
):
    proj_cfg_data = FAKE_PROJ_CFG_BY_VER[proj_tmpl_ver].copy()
    proj_cfg_data.update(proj_cfg or {})
    with open(".proj.cfg", "w") as fd:
        content = ["[conf]"]
        for k, v in proj_cfg_data.items():
            content.append(f"{k} = {v}")
        fd.write("\n".join(content))
    data = FAKE_MANIFEST_DATA.copy()
    data.update(manifest or {})
    # create empty file
    with open(marker_file, "w") as fd:
        fd.write("")
    # write YAML
    update_yml_file(marker_file, data)
    with open(req_file, "w") as fd:
        fd.write("")
    # Mock proj version file
    ver_file = get_conf_key("version_file_rel_path")

    os.makedirs(ver_file.parent.as_posix(), exist_ok=True)
    with ver_file.open("w") as fd:
        fd.write(proj_version)

    if mock_marabunta_file:
        fake_marabunta_file()


def fake_marabunta_file(source_file_path=None):
    source_file_path = source_file_path or get_fixture_path("fake-marabunta.yml")
    if not os.path.exists("odoo"):
        os.mkdir("odoo")
    with source_file_path.open() as fd_source:
        with get_conf_key("marabunta_mig_file_rel_path").open("w") as fd_dest:
            fd_dest.write(fd_source.read())


@contextmanager
def fake_project_root(make_root=True, **kw):
    runner = CliRunner()
    # TODO: do we really need this click util
    # or tmpfile api is enough?
    with runner.isolated_filesystem():
        if make_root:
            make_fake_project_root(**kw)
        yield runner


def compare_line_by_line(content, expected, sort=False):
    content_lines = [x.strip() for x in content.splitlines() if x.strip()]
    expected_lines = [x.strip() for x in expected.splitlines() if x.strip()]
    if sort:
        content_lines = sorted(content_lines)
        expected_lines = sorted(expected_lines)
    # Compare line by line to ease debug in case of error
    for content_line, expected_line in zip(content_lines, expected_lines):
        assert content_line == expected_line, f"{content_line} != {expected_line}"


PENDING_MERGE_FILE_TMPL = """
../odoo/external-src/{repo_name}:
  remotes:
    camptocamp: git@github.com:camptocamp/{repo_name}.git
    OCA: git@github.com:OCA/{repo_name}.git
  target: camptocamp merge-branch-{pid}-master
  merges:
  - OCA 14.0
  - OCA refs/pull/774/head
  - OCA refs/pull/773/head
  - OCA refs/pull/663/head
  - OCA refs/pull/759/head
"""


def mock_pending_merge_repo_paths(repo_name, src=True, pending=True):
    """Generate fake paths for given repo."""
    repo = Repo(repo_name, path_check=False)
    if src:
        path = repo.abs_path / ".git"
        os.makedirs(path, exist_ok=True)

    if pending:
        path = repo.abs_merges_path
        os.makedirs(path.parent, exist_ok=True)
        with open(path, "w") as fd:
            fd.write(PENDING_MERGE_FILE_TMPL.format(repo_name=repo_name, pid="1234"))
