# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import fileinput
import operator
from pathlib import Path

import requirements

from ..config import get_conf_key
from . import ui
from .gh import parse_github_url
from .path import root_path
from .pypi import pkg_name_to_odoo_name

# https://requirements-parser.readthedocs.io/en/latest/


def get_project_req():
    return root_path() / "requirements.txt"


def get_project_dev_req():
    return root_path() / "dev_requirements.txt"


def get_requirements(req_filepath=None):
    req_filepath = Path(req_filepath or get_project_req())
    res = {}
    with req_filepath.open() as fd:
        for req in requirements.parse(fd):
            res[req.name] = req
    return res


def get_addon_requirement(addon, req_filepath=None):
    req_filepath = Path(req_filepath or get_project_req())
    with req_filepath.open() as fd:
        for req in requirements.parse(fd):
            if req.name in (addon, pkg_name_to_odoo_name(addon)):
                return req


def make_requirement_line(pkg_name, version=None):
    return pkg_name + (f" == {version}" if version else "")


def make_requirement_line_for_pr(pkg_name, pr, use_wool=False):
    mod_name = pkg_name_to_odoo_name(pkg_name)
    parts = parse_github_url(pr)
    uri = "git+https://github.com/{upstream}/{repo_name}@refs/{entity_type}/{entity_id}/head".format(
        **parts
    )
    subdirectory = modname_to_installation_subdirectory(mod_name, use_wool)
    return f"{pkg_name} @ {uri}#subdirectory={subdirectory}"


def modname_to_installation_subdirectory(mod_name: str, use_wool: bool):
    if use_wool:
        subdirectory = f"{mod_name}"
    else:
        subdirectory = f"setup/{mod_name}"
    return subdirectory


def make_requirement_line_for_proj_fork(
    pkg_name, repo_name, branch, upstream=None, use_wool=False
):
    upstream = upstream or get_conf_key("company_git_remote")
    mod_name = pkg_name_to_odoo_name(pkg_name)
    parts = {
        "upstream": upstream,
        "branch": branch,
        "repo_name": repo_name,
    }
    uri = "git+https://github.com/{upstream}/{repo_name}@{branch}".format(**parts)
    subdirectory = modname_to_installation_subdirectory(mod_name, use_wool)
    return f"{pkg_name} @ {uri}#subdirectory={subdirectory}"


def make_requirement_line_for_editable(
    pkg_name, pr=None, repo_name=None, dev_src=None, use_wool=False
):
    assert pr or repo_name
    if pr:
        parts = parse_github_url(pr)
        repo_name = parts["repo_name"]
    dev_src = dev_src or get_conf_key("ext_src_rel_path")
    mod_name = pkg_name_to_odoo_name(pkg_name)
    subdirectory = modname_to_installation_subdirectory(mod_name, use_wool)
    return f"-e {dev_src}/{repo_name}/{subdirectory}"


def add_requirement(
    pkg_name, version=None, req_filepath=None, pr=None, editable=False, use_wool=None
):
    req_filepath = Path(req_filepath or get_project_req())
    if use_wool is None:
        # assume a project on Odoo 17 is using wool
        use_wool = version is None or version >= "17"
    if pr:
        handler = make_requirement_line_for_pr
        if editable:
            handler = make_requirement_line_for_editable
        line = handler(pkg_name, pr, use_wool=use_wool)
    else:
        line = make_requirement_line(pkg_name, version=version)
    sep = "\n" if req_filepath.exists() else ""
    with req_filepath.open("a") as fd:
        fd.write(sep + line)


def replace_requirement(
    pkg_name, version=None, req_filepath=None, pr=None, editable=False, use_wool=None
):
    req_filepath = req_filepath or get_project_req()
    if use_wool is None:
        # assume a project on Odoo 17 is using wool
        use_wool = version >= "17"
    if pr:
        handler = make_requirement_line_for_pr
        if editable:
            handler = make_requirement_line_for_editable
        replacement_line = handler(pkg_name, pr, use_wool=use_wool)
    else:
        replacement_line = make_requirement_line(
            pkg_name,
            version=version,
        )
    for line in fileinput.input(req_filepath, inplace=True):
        # `print` replaces line inside fileinput ctx manager
        # TODO: add tests for all the forms of requirements
        if pkg_name in line or pkg_name_to_odoo_name(pkg_name) in line:
            line = replacement_line
        # NOTE: this will add an empty line at the end w/ `\n`
        ui.echo(line)


OP = {
    "==": operator.eq,
    "<=": operator.le,
    ">=": operator.ge,
    ">": operator.gt,
    "<": operator.lt,
}


def allowed_version(req, check_version):
    return all(OP[oper](check_version, version) for (oper, version) in req.specs)
