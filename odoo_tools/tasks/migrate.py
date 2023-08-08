# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import collections
import csv
import json
import os
import sys

import git
import oca_port
from invoke import task

from ..utils.path import cd
from .database import get_db_request_result

ANALYZE_SUBMODULES_TO_SKIP = []
ANALYZE_SUBMODULES = {
    # default: {"upstream": "OCA"}
    "odoo-cloud-platform": {"upstream": "camptocamp"},
    "odoo-enterprise-addons": {"upstream": "camptocamp"},
    "wms-workload": {"upstream": "camptocamp"},
    "odoo-shopinvader": {"upstream": "shopinvader"},
    "odoo-shopinvader-payment": {"upstream": "shopinvader"},
    "ddmrp-professional": {"upstream": "ForgeFlow"},
    "forecasting": {"upstream": "ForgeFlow"},
}


def _get_installed_local_addons(ctx, database_name):
    # Get the local addons
    local_addons = [
        os.path.basename(addon)
        for addon in os.scandir("./odoo/local-src/")
        if addon.is_dir()
    ]
    sql = """
        SELECT name
        FROM ir_module_module
        WHERE state IN ('to install', 'to upgrade', 'installed')
        AND name IN {addons}
        ORDER BY name;
    """.format(
        addons=tuple(local_addons)
    )
    return [row[0] for row in get_db_request_result(ctx, database_name, sql)]


def _get_all_external_addons():
    """Return all addons located in `odoo/external-src/`."""
    external_addons = {}
    external_addons_by_repo = collections.defaultdict(list)
    for repo in os.scandir("./odoo/external-src/"):
        repo_name = os.path.basename(repo)
        if repo_name in ("enterprise",) or not repo.is_dir():
            continue
        for addon_dir in os.scandir(repo.path):
            addon = os.path.basename(addon_dir)
            if not addon_dir.is_dir():
                continue
            addon_files = [f.name for f in os.scandir(addon_dir)]
            if "__manifest__.py" in addon_files:
                external_addons[addon] = repo_name
                external_addons_by_repo[repo_name].append(addon)
    return external_addons_by_repo, external_addons


def _get_installed_external_addons(ctx, database_name, all_external_addons=None):
    """Return installed addons located in `odoo/external-src/`."""
    if not all_external_addons:
        __, all_addons = _get_all_external_addons()
    sql = """
        SELECT name
        FROM ir_module_module
        WHERE state IN ('to install', 'to upgrade', 'installed')
        AND name IN {addons}
        ORDER BY name;
    """.format(
        addons=tuple(all_addons)
    )
    addons = {}
    addons_by_repo = collections.defaultdict(list)
    for row in get_db_request_result(ctx, database_name, sql):
        if row[0] in all_addons:
            repo = all_addons[row[0]]
            addons[row[0]] = repo
            addons_by_repo[repo].append(row[0])
    return addons_by_repo, addons


def _get_addons_dependencies(ctx, database_name, addons):
    # Get module dependencies
    sql = """
        SELECT imm.name as "module", immd.name as "dependency"
        FROM ir_module_module_dependency AS immd LEFT JOIN ir_module_module imm
        ON imm.id = immd.module_id
        WHERE imm.name IN {addons}
        AND immd.name IN {addons}
    """.format(
        addons=tuple(addons)
    )
    # WHERE imm.state IN ('installed', 'to upgrade', 'to install')
    # AND author ILIKE '%Odoo Community Association%';
    dependencies = collections.defaultdict(list)
    for module, dependency in get_db_request_result(ctx, database_name, sql):
        dependencies[module].append(dependency)
    return dependencies


@task(name='analyze-addons')
def analyze_addons(ctx, from_branch, to_branch, database_name):
    """Get a migration report of modules.

    Modules belonging to `odoo/local-src` will be listed as `to migrate`,
    while OCA modules will be analyzed by `oca-port` PRs to check if they
    could to be migrated, or if some commits/PRs could be ported.
    """
    if not os.environ.get("GITHUB_TOKEN"):
        sys.exit(
            "Please set your GitHub token in the GITHUB_TOKEN environment variable."
        )
    # Get all external addons (even not installed ones)
    all_external_addons_by_repo, all_external_addons = _get_all_external_addons()
    # Get external addons (OCA and non-OCA)
    external_addons_by_repo, external_addons = _get_installed_external_addons(
        ctx, database_name
    )
    # Get local addons
    local_addons = _get_installed_local_addons(ctx, database_name)
    # Get module dependencies
    dependencies = _get_addons_dependencies(
        ctx, database_name, list(external_addons) + local_addons
    )
    # Sort OCA addons by submodule path
    addons_to_check = collections.defaultdict(list)
    ordered_external_addons = collections.OrderedDict(
        sorted(external_addons.items(), key=lambda e: e[1])
    )
    for addon, repo_name in ordered_external_addons.items():
        addon_path = os.path.join("odoo", "external-src", repo_name, addon)
        addon_repo_path = os.path.normpath(os.path.join(addon_path, ".."))
        if repo_name in ANALYZE_SUBMODULES_TO_SKIP:
            del external_addons[addon]
            continue
        upstream = upstream_org = ANALYZE_SUBMODULES.get(
            repo_name, {"upstream": "OCA"}
        )["upstream"]
        # Process all other submodules as if they were part of OCA.
        # This allows to analyzed repositories organized like in OCA
        # (e.g. odoo-shopinvader)
        remote_url = f"git@github.com:{upstream_org}/{repo_name}.git"
        with cd(addon_repo_path):
            repo = git.Repo()
            remote_urls = [remote.url for remote in repo.remotes]
            # If the upstream remote exists, get its name
            if remote_url in remote_urls:
                remote_name = repo.remotes[remote_urls.index(remote_url)].name
            # Add the upstream remote if it doesn't exist
            else:
                remote_name = upstream
                if remote_name in [r.name for r in repo.remotes]:
                    repo.delete_remote(remote_name)
                repo.create_remote(remote_name, remote_url)
            addons_to_check[(addon_repo_path, remote_name, upstream_org)].append(addon)
    print(
        f"{len(external_addons)} external addons to check in {len(addons_to_check)} "
        f"submodules + {len(local_addons)} local addons to migrate..."
    )
    # Analyse OCA addons by submodule path
    addons_to_port = collections.defaultdict(dict)
    addons_counter = 0
    enum_addons_to_check = enumerate(addons_to_check.items(), start=1)
    for i, ((repo_path, remote, upstream_org), addons) in enum_addons_to_check:
        print(f"{i}) Analyze {repo_path}...")
        repo_name = os.path.basename(repo_path)
        repo_id = f"{upstream_org}/{repo_name}"
        # Fetch the source & target branches on the first iteration
        fetch = True
        for addon in addons:
            # Initialize the oca-port app
            params = {
                "from_branch": from_branch,
                "to_branch": to_branch,
                "addon": addon,
                "upstream_org": upstream_org,
                "upstream": remote,
                "repo_path": repo_path,
                "repo_name": repo_name,
                "output": "json",
                "fetch": fetch,
            }
            try:
                app = oca_port.App(**params)
            except git.exc.GitCommandError as exc:
                data = {
                    "process": "migrate",
                    "results": {},
                    "warning": str(exc),
                }
                addons_counter += 1
                addons_to_port[repo_id][addon] = data
                continue
            if not app.check_addon_exists_from_branch():
                data = {
                    "process": "migrate",
                    "results": {},
                    "warning": f"not merged in {from_branch} yet",
                }
            else:
                data = json.loads(app.run())
            addons_counter += 1
            addons_to_port[repo_id][addon] = data
            fetch = False
    print(f"{addons_counter} external addons have been analyzed.")
    # Add local addons to this list
    for addon in local_addons:
        addons_to_port["local-src"][addon] = {
            "process": "migrate",
            "results": {},
        }
    # Generate the report
    report_path = f"{database_name}_oca_report"
    report_csv_path = f"{report_path}.csv"
    report_json_path = f"{report_path}.json"
    #   - csv
    with open(report_csv_path, "w") as file_:
        fields = [
            "oca_repository",
            "addon",
            "dependencies",
            "status",
            "info",
            "warning",
        ]
        writer = csv.DictWriter(file_, fields)
        writer.writeheader()
        for repo_name in addons_to_port:
            for addon in addons_to_port[repo_name]:
                data = addons_to_port[repo_name][addon]
                if not data:
                    # Nothing to migrate/port, but list the module anyway
                    data = {"process": "available"}
                info = ""
                if data["process"] == "migrate":
                    if data["results"].get("existing_pr"):
                        data["process"] = "review"
                        info = data["results"]["existing_pr"]["url"]
                elif data["process"] == "port_commits":
                    commits = [pr["missing_commits"] for pr in data["results"].values()]
                    nb_commits = len(commits)
                    info = f"{nb_commits} commits to check/port"
                    info = "\n".join(
                        [info] + [f"- {pr['url']}" for pr in data["results"].values()]
                    )
                row = {
                    "oca_repository": repo_name,
                    "addon": addon,
                    "dependencies": "\n".join(dependencies[addon]),
                    "status": data["process"],
                    "info": info,
                    "warning": data.get("warning", ""),
                }
                writer.writerow(row)
    #   - json (ease reports comparison later on)
    with open(report_json_path, "w") as file_:
        json.dump(addons_to_port, file_, indent=4)
    print(f"Reports generated:\n- {report_csv_path}\n- {report_json_path}")
