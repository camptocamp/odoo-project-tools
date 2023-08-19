# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from click.testing import CliRunner

from odoo_tools.config import get_conf_key
from odoo_tools.utils import req as req_utils

from .common import fake_project_root, get_fixture_path

fake_req = get_fixture_path("fake-requirements.txt")


def test_get_requirements():
    # with runner.isolated_filesystem():
    reqs = req_utils.get_requirements(fake_req)
    a1 = reqs["odoo-addon-name1"]
    assert a1.specs == [("==", "1.0.0")]
    a2 = reqs["odoo-addon-name2"]
    assert a2.specs == [("<", "2.0.0")]
    a3 = reqs["oca-port"]
    assert a3.editable
    assert a3.specs == []
    assert a3.uri == "git+git://github.com/OCA/oca-port"
    assert a3.revision == "xyz123"
    assert a3.vcs == "git"
    # a4 = reqs["odoo14-addon-edi_state_oca"]
    # TODO: no version found here
    # {'editable': False,
    # 'extras': [],
    # 'hash': None,
    # 'hash_name': None,
    # 'line': 'odoo14-addon-edi_state_oca @ git+https://github.com/OCA/edi-framework@refs/pull/2/head#subdirectory=setup/edi_state_oca',
    # 'local_file': False,
    # 'name': 'odoo14-addon-edi_state_oca',
    # 'path': None,
    # 'revision': None,
    # 'specifier': True,
    # 'specs': [],
    # 'subdirectory': None,
    # 'uri': None,
    # 'vcs': None}
    a5 = reqs["nice_addon"]
    assert a5.editable


def test_get_addon_requirement():
    a1 = req_utils.get_addon_requirement("odoo-addon-name1", req_filepath=fake_req)
    assert a1.specs == [("==", "1.0.0")]


def test_make_requirement_line():
    assert req_utils.make_requirement_line("foo", version="1.2.0") == "foo == 1.2.0"
    assert req_utils.make_requirement_line("odoo-addon-bla") == "odoo-addon-bla"


def test_make_requirement_line_for_pr():
    make = req_utils.make_requirement_line_for_pr
    mod_name = "edi_record_metadata_oca"
    pkg_name = f"odoo14-addon-{mod_name}"
    pr = "https://github.com/OCA/edi-framework/pull/3"
    expected = "odoo14-addon-edi_record_metadata_oca @ git+https://github.com/OCA/edi-framework@refs/pull/3/head#subdirectory=setup/edi_record_metadata_oca"
    assert make(pkg_name, pr) == expected


def test_make_requirement_line_for_pr_editable():
    with fake_project_root():
        make = req_utils.make_requirement_line_for_editable
        mod_name = "edi_record_metadata_oca"
        pkg_name = f"odoo14-addon-{mod_name}"
        pr = "https://github.com/OCA/edi-framework/pull/3"
        path = get_conf_key("ext_src_rel_path")
        expected = f"-e {path}/edi-framework/setup/edi_record_metadata_oca"
        assert make(pkg_name, pr) == expected


def test_add_requirement():
    runner = CliRunner()
    with runner.isolated_filesystem():
        req_path = "./tmp-requirements.txt"
        req_utils.add_requirement("foo", version="1.2.3", req_filepath=req_path)
        with open(req_path) as fd:
            assert fd.read() == "foo == 1.2.3"
        req_utils.add_requirement("baz", version="2.2.3", req_filepath=req_path)
        with open(req_path) as fd:
            assert fd.read() == "foo == 1.2.3\nbaz == 2.2.3"


def test_add_requirement_pr():
    runner = CliRunner()
    with runner.isolated_filesystem():
        req_path = "./tmp-requirements.txt"
        pr = "https://github.com/OCA/edi-framework/pull/3"
        mod_name = "foo"
        pkg_name = f"odoo-addon-{mod_name}"
        req_utils.add_requirement(pkg_name, pr=pr, req_filepath=req_path)
        expected = "odoo-addon-foo @ git+https://github.com/OCA/edi-framework@refs/pull/3/head#subdirectory=setup/foo"
        with open(req_path) as fd:
            assert fd.read() == expected


def test_add_requirement_pr_editable():
    with fake_project_root():
        req_path = "./tmp-requirements.txt"
        pr = "https://github.com/OCA/edi-framework/pull/3"
        mod_name = "foo"
        pkg_name = f"odoo-addon-{mod_name}"
        req_utils.add_requirement(pkg_name, pr=pr, req_filepath=req_path, editable=True)
        path = get_conf_key("ext_src_rel_path")
        expected = f"-e {path}/edi-framework/setup/{mod_name}"
        with open(req_path) as fd:
            assert fd.read() == expected


def test_replace_requirement():
    runner = CliRunner()
    with runner.isolated_filesystem():
        req_path = "./tmp-requirements.txt"
        pr = "https://github.com/OCA/edi-framework/pull/3"
        mod_name = "foo"
        pkg_name = f"odoo-addon-{mod_name}"
        req_utils.add_requirement(pkg_name, pr=pr, req_filepath=req_path)
        req_utils.replace_requirement(pkg_name, version="1.0.0", req_filepath=req_path)
        expected = "odoo-addon-foo == 1.0.0\n"
        with open(req_path) as fd:
            assert fd.read() == expected


def test_allowed_version():
    a2 = req_utils.get_addon_requirement("odoo-addon-name2", req_filepath=fake_req)
    assert req_utils.allowed_version(a2, "1.8.0")
    assert not req_utils.allowed_version(a2, "2.0.1")
    assert not req_utils.allowed_version(a2, "2.1.0")


def test_make_requirement_line_for_proj_fork():
    with fake_project_root():
        r1 = req_utils.make_requirement_line_for_proj_fork(
            "odoo-addon-name2", "social", "14.0"
        )
        assert (
            r1
            == "odoo-addon-name2 @ git+https://github.com/camptocamp/social@14.0#subdirectory=setup/name2"
        )
