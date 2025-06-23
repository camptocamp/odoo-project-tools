#! /usr/bin/env python3
"""
Helper to migrate "old" format project to the new image format.

Please delete this when our last project has been converted.
"""

import argparse
import ast
import configparser
import glob
import os
import os.path as osp
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from ..config import get_conf_key
from ..utils.path import root_path
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

    * update the ADDONS_PATH environment variable (`odoo/src` and
      `odoo/external-src/enterprise` have moved,
      `odoo-cloud-platform` must be removed)
    * check other environment variables which could have been set
    * check the differences introduced by an ongoing migration process

   meld Dockerfile Dockerfile.bak


2. check the diff between docker-compose.yml and docker-compose.yml.bak

    meld docker-compose.yml docker-compose.yml.bak

3. if you had a previous docker-compose.override.yml file, and you created a
   backup before synchronizing the project, you can merge it with the new one

4. check for pending merges in odoo or enterprise, and make sure you have patch
   files for these that are placed in patches/odoo and patches/enterprise/
   respectively. They will be processed by alphabetical order.

5. run `docker build .` and fix any build issues

6. configure github actions on your repository -> see
   https://confluence.camptocamp.com/confluence/display/DEV/How+to+deploy+Github+Actions+on+odoo+projects

7. run your project and be happy!

Try building the image with:

docker build .

"""


def main(args=None):
    if get_conf_key("template_version") == 2:
        print("Project already migrated")
        return sys.exit(0)
    if args is None:
        args = parse_args()

    # ensure project root is found
    root_path()
    move_files()
    submodules = collect_submodules()
    init_proj_v2()
    remove_submodules(submodules)
    remove_files()
    copy_dockerfile()
    report(NEXT_STEPS_MSG)
    generate_report()


@dataclass
class Submodule:
    name: str
    path: str = ""
    url: str = ""
    branch: str = ""

    def generate_requirements(self, installed_modules):
        """return a block concerning the submodule that can be inserted in a requirements.txt file.

        The block has 1 line per module which is in the repository
        """
        odoo_serie = get_current_version(serie_only=True)
        if self.name in ("odoo/src", "odoo/external-src/enterprise"):
            return ""
        manifest_paths = glob.glob(self.path + "/*/__manifest__.py")
        require = [f"# {self.name}"]
        for manifest_path in manifest_paths:
            addon = osp.basename(osp.dirname(manifest_path))
            if addon.startswith("test_"):
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

    to_remove = [
        "odoo/src",
        "odoo/external-src/enterprise",
        "odoo/external-src/odoo-cloud-platform",
    ]
    sections_to_remove = [f'submodule "{path}"' for path in to_remove]
    for section in submodules:
        if section not in sections_to_remove:
            continue
        parser.remove_section(section)
        subprocess.run(["git", "rm", "-f", submodules[section].path], check=False)


def init_proj_v2():
    subprocess.run(["rm", ".proj.cfg"], check=False)
    env = dict(os.environ, PROJ_TMPL_VER="2")
    subprocess.run(["otools-project", "init"], env=env, check=False)
    subprocess.run(
        [
            "git",
            "add",
            ".bumpversion.cfg",
            ".proj.cfg",
        ],
        check=False,
    )


def move_files():
    if os.path.isdir("odoo/local-src/server_environment_files"):
        # the project has a server_environment_files module -> use this one
        subprocess.run(
            ["git", "rm", "-f", "-r", "odoo/addons/server_environment_files"],
            check=False,
        )
    if glob.glob("odoo/local-src/*bundle"):
        # the project is already using bundles -> drop the one generated by sync
        for dirname in glob.glob("odoo/addons/*bundle"):
            subprocess.run(["git", "rm", "-f", "-r", dirname], check=False)

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
                "camptocamp_tools",
                "camptocamp_website_tools",
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
        subprocess.run(["git", "mv", "-f", filename, destdir], check=False)

    # the Dockerfile expect the patches/ directory to exist
    if not os.path.isdir("patches"):
        os.mkdir("patches")
        open("patches/.gitkeep", "w").close()
        subprocess.run(["git", "add", "patches/.gitkeep"], check=False)


def remove_files():
    """cleanup no longer needed files"""
    to_remove = [
        "tasks",
        "odoo/before-migrate-entrypoint.d",
        "odoo/bin",
        "odoo/start-entrypoint.d",
        "odoo/setup.py",
        "docs",
        # "odoo/local-src/camptocamp_tools",
        # "odoo/local-src/camptocamp_website_tools",
    ]
    for name in to_remove:
        if osp.isdir(name):
            # shutil.rmtree(name)
            subprocess.run(["git", "rm", "-f", "-r", name], check=False)

        elif osp.isfile(name):
            # os.unlink(name)
            subprocess.run(["git", "rm", "-f", name], check=False)
        else:
            raise ValueError(f"unexpected file {name}. Is it a symlink?")


def copy_dockerfile():
    shutil.move("odoo/Dockerfile", "Dockerfile.bak")
    subprocess.run(["git", "rm", "-f", "odoo/Dockerfile"], check=False)


def parse_args():
    parser = argparse.ArgumentParser(
        "Project Converter",
        "Tool to convert projects to the new docker image format",
        epilog="For a step by step guide on how to use this tool, check "
        "https://github.com/camptocamp/odoo-project-tools#project-conversion",
    )

    args = parser.parse_args()
    return args


if __name__ == "__main__":
    main()
