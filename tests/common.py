# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import os
from contextlib import contextmanager
from pathlib import PosixPath

from click.testing import CliRunner

from odoo_tools.utils import pending_merge as pm_utils
from odoo_tools.utils.config import config
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
    template_version="1",
    company_git_remote="camptocamp",
    odoo_src_rel_path="odoo/src",
    ext_src_rel_path="odoo/external-src",
    local_src_rel_path="odoo/local-src",
    pending_merge_rel_path="pending-merges.d",
    version_file_rel_path="odoo/VERSION",
    marabunta_mig_file_rel_path="odoo/migration.yml",
)
FAKE_PROJ_CFG_V2 = dict(
    template_version="2",
    company_git_remote="camptocamp",
    odoo_src_rel_path="src",
    ext_src_rel_path="odoo/dev-src",
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
    marker_file=None,
    req_file="requirements.txt",
    proj_version="14.0.0.1.0",
    mock_marabunta_file=False,
    extra_files=None,
):
    if marker_file is None:
        marker_file = get_root_marker()
    proj_cfg_data = FAKE_PROJ_CFG_BY_VER[str(proj_tmpl_ver)].copy()
    proj_cfg_data.update(proj_cfg or {})
    with open(".proj.cfg", "w") as fd:
        content = ["[conf]"]
        for k, v in proj_cfg_data.items():
            content.append(f"{k} = {v}")
        fd.write("\n".join(content))
    config._reload()
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
    ver_file = config.version_file_rel_path

    os.makedirs(ver_file.parent.as_posix(), exist_ok=True)
    with ver_file.open("w") as fd:
        fd.write(proj_version)

    if mock_marabunta_file:
        fake_marabunta_file()
    # Write the extra files
    if extra_files:
        for path, content in extra_files.items():
            with open(path, "w") as fd:
                fd.write(content)


def fake_marabunta_file(source_file_path=None):
    source_file_path = source_file_path or get_fixture_path("fake-marabunta.yml")
    if not os.path.exists("odoo"):
        os.mkdir("odoo")
    with source_file_path.open() as fd_source:
        with config.marabunta_mig_file_rel_path.open("w") as fd_dest:
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
../{ext_src_rel_path}/{repo_name}:
  remotes:
    camptocamp: git@github.com:camptocamp/{repo_name}.git
    {org_name}: git@github.com:{org_name}/{repo_name}.git
  target: camptocamp merge-branch-{pid}-master
  merges:
  - {org_name} 14.0
  - {org_name} refs/pull/774/head
  - {org_name} refs/pull/773/head
  - {org_name} refs/pull/663/head
  - {org_name} refs/pull/759/head
"""


def mock_pending_merge_repo_paths(
    repo_name, org_name="OCA", src=True, pending=True, tmpl=PENDING_MERGE_FILE_TMPL
):
    """Generate fake paths for given repo."""
    repo = Repo(repo_name, path_check=False)
    path = None
    if src:
        path = repo.abs_path / ".git"
        os.makedirs(path, exist_ok=True)

    if pending:
        path = repo.abs_merges_path
        os.makedirs(path.parent, exist_ok=True)
        with open(path, "w") as fd:
            fd.write(
                tmpl.format(
                    ext_src_rel_path=repo.ext_src_rel_path,
                    repo_name=repo_name,
                    org_name=org_name,
                    pid="1234",
                )
            )
    return path


class MockCompletedProcess:
    def __init__(self, args=None, stdout=None, returncode=0):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout


def mock_subprocess_run(mock_spec=None):
    """Return a function that you can pass to unittest.mock.patch:

    with patch("subprocess.run", mock_subprocess_run(spec)):
        do your test

    mock_speck is a list of dictionaries. The entries are used to match
    subsequent calls to subprocess.run(), in order.

    Each directory has the following keys:

    args: (required) the arguments that subprocess.run() is expected to be called with.
    If this is a callable, then it is run with the args received and is expected to test them and return True

    stdout: (optional) a string that will be used as the output of the command

    sim_call: (optional) a callable that will be executed instead of the process

    sim_call_args: (optional) a list of positional parameters to `sim_call`

    sim_call_kwargs: (optional) a list of named parameters to `sim_call`

    The mock returns a MockCompletedProcess object. If stdout is not None, the string or bytes object
    passed is is the `stdout` attribute of that object.
    """
    if mock_spec is None:
        mock_spec = []

    def mock_run(args, stdout=None, **kwargs):
        call_spec = mock_spec.pop(0)
        if call_spec["args"] is not None:
            if callable(call_spec["args"]):
                assert call_spec["args"](
                    args
                ), f"subprocess.call({args}): problem with the arguments"
            else:
                assert (
                    args == call_spec["args"]
                ), f"Wrong args {args}, expecting {call_spec['args']}"
        if "sim_call" in call_spec:
            call_spec["sim_call"](
                *call_spec.get(
                    "sim_call_args", [], **call_spec.get("sim_call_kwargs", {})
                )
            )
        return MockCompletedProcess(args, stdout=call_spec.get("stdout"))

    def assert_completed_calls():
        assert not mock_spec, f"{len(mock_spec)} calls missing: {mock_spec}"

    mock_run.assert_completed_calls = assert_completed_calls

    return mock_run
