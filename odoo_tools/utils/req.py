# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import fileinput
import operator
import os

import requirements

from .gh import parse_github_url
from .path import root_path
from .pypi import pkg_name_to_odoo_name

# https://requirements-parser.readthedocs.io/en/latest/


def get_project_req():
    return root_path() / "requirements.txt"


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
            if req.name == addon:
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


def add_requirement(pkg_name, version=None, req_filepath=None, pr=None):
    req_filepath = req_filepath or get_project_req()
    if pr:
        line = make_requirement_line_for_pr(pkg_name, pr)
    else:
        line = make_requirement_line(pkg_name, version=version)
    sep = "\n" if os.path.exists(req_filepath) else ""
    with open(req_filepath, "a") as fd:
        fd.write(sep + line)


def replace_requirement(pkg_name, version=None, req_filepath=None, pr=None):
    if pr:
        replacement_line = make_requirement_line_for_pr(pkg_name, pr)
    else:
        replacement_line = make_requirement_line(pkg_name, version=version)
    req_filepath = req_filepath or get_project_req()
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
