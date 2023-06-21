# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import fileinput
import operator
import os

import requirements

from ..config import get_conf_key
from .gh import parse_github_url
from .path import root_path
from .pypi import pkg_name_to_odoo_name

# https://requirements-parser.readthedocs.io/en/latest/


def get_project_req():
    return root_path() / "requirements.txt"


def get_project_dev_req():
    return root_path() / "dev-requirements.txt"


def get_requirements(req_filepath=None):
    req_filepath = req_filepath or get_project_req()
    res = {}
    with open(req_filepath) as fd:
        for req in requirements.parse(fd):
            res[req.name] = req
    return res


def get_addon_requirement(addon, req_filepath=None):
    req_filepath = req_filepath or get_project_req()
    with open(req_filepath) as fd:
        for req in requirements.parse(fd):
            if req.name in (addon, pkg_name_to_odoo_name(addon)):
                return req


def make_requirement_line(pkg_name, version=None):
    return pkg_name + (f" == {version}" if version else "")


def make_requirement_line_for_pr(pkg_name, pr):
    mod_name = pkg_name_to_odoo_name(pkg_name)
    parts = parse_github_url(pr)
    uri = "git+https://github.com/{upstream}/{repo_name}@refs/{entity_type}/{entity_id}/head".format(
        **parts
    )
    return f"{pkg_name} @ {uri}#subdirectory=setup/{mod_name}"


def make_requirement_line_for_editable(pkg_name, pr=None, repo_name=None, dev_src=None):
    assert pr or repo_name
    if pr:
        parts = parse_github_url(pr)
        repo_name = parts["repo_name"]
    dev_src = dev_src or get_conf_key("ext_src_rel_path")
    mod_name = pkg_name_to_odoo_name(pkg_name)
    return f"-e {dev_src}/{repo_name}/setup/{mod_name}"


def add_requirement(pkg_name, version=None, req_filepath=None, pr=None, editable=False):
    req_filepath = req_filepath or get_project_req()
    if pr:
        handler = make_requirement_line_for_pr
        if editable:
            handler = make_requirement_line_for_editable
        line = handler(pkg_name, pr)
    else:
        line = make_requirement_line(pkg_name, version=version)
    sep = "\n" if os.path.exists(req_filepath) else ""
    with open(req_filepath, "a") as fd:
        fd.write(sep + line)


def replace_requirement(
    pkg_name, version=None, req_filepath=None, pr=None, editable=False
):
    req_filepath = req_filepath or get_project_req()
    if pr:
        handler = make_requirement_line_for_pr
        if editable:
            handler = make_requirement_line_for_editable
        replacement_line = handler(pkg_name, pr)
    else:
        replacement_line = make_requirement_line(pkg_name, version=version)
    for line in fileinput.input(req_filepath, inplace=True):
        # `print` replaces line inside fileinput ctx manager
        if pkg_name in line:
            line = replacement_line
        # NOTE: this will add an empty line at the end w/ `\n`
        print(line)


OP = {
    "==": operator.eq,
    "<=": operator.le,
    ">=": operator.ge,
    ">": operator.gt,
    "<": operator.lt,
}


def allowed_version(req, check_version):
    for _op, version in req.specs:
        op = OP[_op]
        if not op(check_version, version):
            return False
    return True
