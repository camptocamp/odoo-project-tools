#! /usr/bin/env python3
"""
Helper to migrate "old" format project to the new image format.

Please delete this when our last project has been converted.
"""
import argparse
import ast
import configparser
import getpass
import glob
import os
import os.path as osp
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

import odoorpc

from ..config import get_conf_key
from ..utils.path import root_path
from ..utils.pending_merge import Repo
from ..utils.proj import get_current_version
from ..utils.pypi import odoo_name_to_pkg_name
from ..utils.req import make_requirement_line_for_proj_fork

REPORT = []


def report(msg):
    global REPORT
    REPORT.append(msg)


def generate_report():
    global REPORT
    content = "\n".join(REPORT)
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print(content)
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    next_steps_todo = "V2_MIG_NEXT_STEPS.todo"
    with open(next_steps_todo, "w") as fd:
        fd.write(content)
    print(
        "You can find this summary in", next_steps_todo, "file at the root of the proj."
    )


NEXT_STEPS_MSG = """\
Next steps
==========

1. check the diff between Dockerfile and Dockerfile.bak.
   Look especially for

    * the environment variables
    * ADDONS_PATH

   meld Dockerfile Dockerfile.bak


# TODO: there's no such backup file -> the sync will replace it

2. check the diff between docker-compose.yml and docker-compose.yml.bak

    meld docker-compose.yml docker-compose.yml.bak

3. check for pending merges in the OCA addons, and edit requirements.txt to match these (see below)
4. check for pending merges in odoo or enterprise and find a way to cope with this XXXXX
5. run docker build . and fix any build issues
6. run your project and be happy!

Try building the image with:

docker build .

"""

PENDING_MERGE_MSG = """
Repo(s) with pending merges
===========================

{repos_with_pending_merges}

You can check PRs with: `otools-pending show path/to/repo`.

Handling pending merges
=======================

If you have some pending merges, for instance in pending-merges/bank-payment.yml:

```
../odoo/external-src/bank-payment:
  remotes:
    camptocamp: git@github.com:camptocamp/bank-payment.git
    OCA: git@github.com:OCA/bank-payment.git
  target: camptocamp merge-branch-12345-master
  merges:
  - OCA $pinned-base
  - OCA refs/pull/978/head
```

you need to do the following:
1. check which addon is affected by the PR
2. run

    otools-addon add mod1 https://github.com/OCA/bank-payment/pull/978
    otools-addon add mod2 https://github.com/OCA/bank-payment/pull/978

If you need/want to add requirements manually you can use

    otools-addon print-req mod1 [-p $pr] [-b $branch] [...]

to generate the line to add.
"""


def main(args=None):
    if get_conf_key("template_version") == "2":
        print("Project already migrated")
        return sys.exit(0)
    if args is None:
        args = parse_args()

    if args.disable_module_fetching:
        installed_modules = set()
    else:
        installed_modules = get_installed_modules(
            args.instance_host,
            args.instance_port,
            args.instance_database,
            args.admin_login,
            args.admin_password,
        )
    # ensure project root is found
    root_path()
    move_files()
    submodules = collect_submodules()
    init_proj_v2()
    handle_submodule_requirements(submodules.values(), installed_modules)
    remove_submodules(submodules)
    remove_files()
    copy_dockerfile()
    report(NEXT_STEPS_MSG)
    generate_report()


def get_installed_modules(host, port, dbname, login, password):
    if port == 443:
        protocol = "jsonrpc+ssl"
    else:
        protocol = "jsonrpc"
    odoo = odoorpc.ODOO(host, port=port, protocol=protocol)
    odoo.login(dbname, login, password)
    modules = odoo.execute(
        'ir.module.module', 'search_read', [('state', '=', 'installed')], ['name']
    )
    installed_modules = set()
    for values in modules:
        installed_modules.add(values['name'])
    return installed_modules


@dataclass
class Submodule:
    name: str
    path: str = ""
    url: str = ""
    branch: str = ""

    def generate_requirements(self, installed_modules):
        """return a block concerning the submodule thatn can be inserted in a requirements.txt file.

        The block has 1 line per module which is in the repository
        """
        odoo_serie = get_current_version(serie_only=True)
        if self.name in ("odoo/src", "odoo/external-src/enterprise"):
            return ""
        manifest_paths = glob.glob(self.path + "/*/__manifest__.py")
        require = [f"# {self.name}"]
        for manifest_path in manifest_paths:
            addon = osp.basename(osp.dirname(manifest_path))
            if addon.startswith('test_'):
                continue
            # an empty installed_modules set means we disabled fetching
            # installed modules -> in that case we get everything
            if installed_modules and addon not in installed_modules:
                # skip uninstalled addons
                continue
            addon_pypi_name = odoo_name_to_pkg_name(addon, odoo_serie=odoo_serie)
            with open(manifest_path) as man_fp:
                manifest = ast.literal_eval(man_fp.read())

            version = manifest["version"]
            if not version.startswith(odoo_serie):
                continue
            if self.name.endswith("odoo-cloud-platform"):
                # XXX to rework when these are published on pypi (we will still probably need to force a version
                branch = f"{odoo_serie}.0"  # FIXME: use target branch
                require.append(
                    make_requirement_line_for_proj_fork(
                        addon_pypi_name,
                        "odoo-cloud-platform",
                        branch,
                    )
                )
            else:
                require.append(f"{addon_pypi_name} >= {version}, == {version}.*")
            break
        return "\n".join(require)


def collect_submodules():
    """remove the submodules from the project"""
    submodules = {}
    parser = configparser.ConfigParser()
    parser.read(".gitmodules")
    for section in parser:
        if section.startswith("submodule"):
            print(section)
            name = re.match(r"""submodule ['"]([\w/_-]+)['"]""", section).groups(1)[0]
            submodule = Submodule(name=name)
            submodules[section] = submodule
            for fieldname, value in parser[section].items():
                print(fieldname, value)
                submodule.__setattr__(fieldname, value)
    return submodules


def remove_submodules(submodules):
    parser = configparser.ConfigParser(strict=False)
    parser.read(".git/config")
    for section in submodules:
        parser.remove_section(section)
        subprocess.run(["git", "rm", "--cached", submodules[section].path])
        shutil.rmtree(submodules[section].path)
    parser.write(open(".git/config2", "w"))
    subprocess.run(["git", "rm", "-f", ".gitmodules"])
    subprocess.run(["git", "rm", "-f", ".git/modules/odoo"])


def handle_submodule_requirements(submodules, installed_modules):
    repos_with_pending_merges = []
    requirements_fp = open("requirements.txt", "a")
    for submodule in submodules:
        requirements = submodule.generate_requirements(installed_modules)
        requirements_fp.write(requirements)
        requirements_fp.write("\n")
        repo = Repo(submodule.name, path_check=False)
        if repo.has_pending_merges():
            repos_with_pending_merges.append(submodule.name)
    requirements_fp.close()
    subprocess.run(["git", "add", "requirements.txt"])

    if repos_with_pending_merges:
        report(
            PENDING_MERGE_MSG.format(
                repos_with_pending_merges='\n -'.join(repos_with_pending_merges)
            )
        )
        # TODO: if we delete submodules before reaching this point
        # devs will have to switch back to master to do such checks.


def init_proj_v2():
    subprocess.run(["rm", ".proj.cfg"])
    env = dict(os.environ, PROJ_TMPL_VER="2")
    subprocess.run(["otools-project", "init"], env=env)


def move_files():
    if os.path.isdir("odoo/local-src/server_environment_files"):
        # the project has a server_environment_files module -> use this one
        subprocess.run(
            ["git", "rm", "-f", "-r", "odoo/addons/server_environment_files"]
        )
    if glob.glob("odoo/local-src/*bundle"):
        # @simo: @alex I don't get this!
        # the project is already using bundles -> drop the one generated by sync
        for dirname in glob.glob("odoo/addons/*bundle"):
            subprocess.run(["git", "rm", "-f", "-r", dirname])

    to_move = [
        ("odoo/VERSION", "."),
        ("odoo/migration.yml", "."),
        ("odoo/data", "."),
        ("odoo/songs", "."),
        ("odoo/patches", "."),
        ("odoo/requirements.txt", "."),
    ] + [
        (submodule, "odoo/addons")
        for submodule in glob.glob("odoo/local-src/*")
        if not submodule.endswith(
            (
                'camptocamp_tools',
                'camptocamp_website_tools',
            )
        )
    ]
    for filename, destdir in to_move:
        destname = osp.join(destdir, osp.basename(filename))
        if osp.isfile(destname):
            os.unlink(destname)
        elif osp.isdir(destname):
            shutil.rmtree(destname)
        # shutil.move(filename, destdir)
        subprocess.run(["git", "mv", "-f", filename, destdir])


def remove_files():
    """cleanup no longer needed files"""
    to_remove = [
        "tasks",
        "odoo/before-migrate-entrypoint.d",
        "odoo/bin",
        "odoo/start-entrypoint.d",
        "odoo/setup.py",
        "docs",
        "travis",
        "odoo/local-src/camptocamp_tools",
        "odoo/local-src/camptocamp_website_tools",
        # "odoo/external-src",
    ]
    for name in to_remove:
        if osp.isdir(name):
            # shutil.rmtree(name)
            subprocess.run(["git", "rm", "-f", "-r", name])

        elif osp.isfile(name):
            # os.unlink(name)
            subprocess.run(["git", "rm", "-f", name])
        else:
            raise ValueError(f'unexpected file {name}. Is it a symlink?')


def copy_dockerfile():
    shutil.move('odoo/Dockerfile', 'Dockerfile.bak')
    subprocess.run(["git", "rm", "-f", "odoo/Dockerfile"])


def parse_args():
    parser = argparse.ArgumentParser(
        "Project Converter", "Tool to convert projects to the new docker image format"
    )
    parser.add_argument(
        "-n",
        "--no-module-from-instance",
        action="store_true",
        dest="disable_module_fetching",
        help="don't fetch the list of installed module from a live Odoo instance",
    )
    parser.add_argument(
        "-i",
        "--instance-host",
        action="store",
        dest="instance_host",
        default="localhost",
    )
    parser.add_argument(
        "-p",
        "--instance-port",
        action="store",
        type=int,
        dest="instance_port",
        default=443,
    )
    parser.add_argument(
        "-d", "--database", action="store", dest="instance_database", default="odoodb"
    )
    parser.add_argument(
        "-a", "--admin", action="store", dest="admin_login", default="admin"
    )
    args = parser.parse_args()
    if not args.disable_module_fetching:
        admin_password = os.getenv("CONV_ADMIN_PWD") or getpass.getpass(
            "Instance admin password: "
        )
        args.admin_password = admin_password

    return args


if __name__ == "__main__":
    main()
