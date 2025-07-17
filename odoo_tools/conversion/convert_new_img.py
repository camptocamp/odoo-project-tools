#! /usr/bin/env python3
"""
Helper to migrate "old" format project to the new image format.

Please delete this when our last project has been converted.
"""

import argparse
import ast
import configparser
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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
    content = "\n".join(REPORT)
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print(content)
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    next_steps_todo = Path("V2_MIG_NEXT_STEPS.todo")
    next_steps_todo.write_text(content)
    print(
        "You can find this summary in", next_steps_todo, "file at the root of the proj."
    )


NEXT_STEPS_MSG = """\
Next steps
==========

1. check the diff between Dockerfile and Dockerfile.bak.

    * check the ADDONS_PATH environment variable: the paths have changed and the script may not know of
      the specificities of your project (esp. paid addons)
    * check other environment variables which could have been set
    * check the differences introduced by an ongoing migration process

   meld Dockerfile Dockerfile.bak


2. check the diff between docker-compose.yml and docker-compose.yml.bak and restore any customizations
   you could have done (environment variables...)

    meld docker-compose.yml docker-compose.yml.bak

3. if you had a previous docker-compose.override.yml file, and you created a
   backup before synchronizing the project, you can merge it with the new one

4. check for pending merges in odoo or enterprise, and make sure you have patch
   files for these that are placed in patches/odoo and patches/enterprise/
   respectively. They will be processed by alphabetical order.

   * if you have patch files in the  `patches/` directory that don't match any pending merge in
     `pending-merges.d/src.yml` or `pending-merges.d/enterprise.yml`, remove them
   * if you have pending merges in `pending-merges.d/src.yml` (resp. `pending-merges.d/enterprise.yml`)
     and you have the matching patch files in the `patches/` directory, move the patch files to `patches/odoo/`
     (resp. `patches/enterprise/`)
   * if you have pending merges in `pending-merges.d/src.yml` (resp. `pending-merges.d/enterprise.yml`)
     but you don't have the matching  patch files in the `patches/`, you can regenerate them with
     `otools-pending add <url-to-commit>`

5. run `docker build .` and fix any build issues. The base Python version may have changed, so you
   could need to update the version of some dependencies that were frozen to be compatible with Python 3.9
   for instance.

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
        manifest_paths = Path(self.path).glob("*/__manifest__.py")
        require = [f"# {self.name}"]
        for manifest_path in manifest_paths:
            addon = manifest_path.parent.name
            if addon.startswith("test_"):
                continue
            # an empty installed_modules set means we disabled fetching
            # installed modules -> in that case we get everything
            if installed_modules and addon not in installed_modules:
                # skip uninstalled addons
                continue
            addon_pypi_name = odoo_name_to_pkg_name(addon, odoo_serie=odoo_serie)
            manifest = ast.literal_eval(manifest_path.read_text())

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
    cwd = Path()
    odoo_dir = cwd / "odoo"
    if (odoo_dir / "local-src/server_environment_files").is_dir():
        # the project has a server_environment_files module -> use this one
        subprocess.run(
            ["git", "rm", "-f", "-r", "odoo/addons/server_environment_files"],
            check=False,
        )
    for dirname in odoo_dir.glob("local-src/*bundle"):
        # the project is already using bundles -> drop the one generated by sync
        subprocess.run(["git", "rm", "-f", "-r", str(dirname)], check=False)

    to_move = [
        ("odoo/VERSION", "."),
        ("odoo/migration.yml", "."),
        ("odoo/data", "."),
        ("odoo/songs", "."),
        ("odoo/patches", "."),
        ("odoo/requirements.txt", "."),
    ] + [
        (submodule, "odoo/addons")
        for submodule in odoo_dir.glob("local-src/*")
        if submodule.name
        not in (
            (
                "camptocamp_tools",
                "camptocamp_website_tools",
            )
        )
    ]
    for filename, destdir in to_move:
        dest = cwd / destdir / (cwd / filename).name
        if dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
        # shutil.move(filename, destdir)
        subprocess.run(["git", "mv", "-f", filename, destdir], check=False)

    # the Dockerfile expect the patches/ directory to exist
    patches_dir = Path("patches")
    if not patches_dir.is_dir():
        patches_dir.mkdir()
        gitkeep = patches_dir / ".gitkeep"
        gitkeep.touch()
        subprocess.run(["git", "add", str(gitkeep)], check=False)


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
        fpth = Path(name)
        if fpth.is_dir():
            # shutil.rmtree(fpth)
            subprocess.run(["git", "rm", "-f", "-r", str(fpth)], check=False)
        elif fpth.is_file():
            # fpth.unlink()
            subprocess.run(["git", "rm", "-f", str(fpth)], check=False)
        else:
            raise ValueError(f"unexpected file {fpth}. Is it a symlink?")


def convert_env_lines(old_env_lines):
    new_env_lines = []
    for line in old_env_lines:
        new_line = (
            line.replace(
                "/odoo/src/addons", "/odoo/src/odoo/odoo/addons, /odoo/src/odoo/addons"
            )
            .replace("/odoo/external-src/paid-modules", "/odoo/odoo/paid-modules")
            .replace("/odoo/external-src/enterprise", "/odoo/src/enterprise")
            .replace("/odoo/external-src", "/odoo/odoo/external-src")
            .replace("/odoo/local-src", "/odoo/odoo/addons")
        )
        if "odoo-cloud-platform" in new_line:
            continue
        new_env_lines.append(new_line)
    return new_env_lines


def copy_dockerfile():
    shutil.move("odoo/Dockerfile", "Dockerfile.bak")
    old_env_lines = []
    with open("Dockerfile.bak") as old_dockerfile:
        found_env = False
        for line in old_dockerfile:
            if line.strip().startswith("ENV ADDONS"):
                found_env = True
            if found_env:
                old_env_lines.append(line)
                if not line.strip().endswith("\\"):
                    found_env = False
    subprocess.run(["git", "rm", "-f", "odoo/Dockerfile"], check=False)
    new_env_lines = convert_env_lines(old_env_lines)
    new_docker_file_lines = []
    with open("Dockerfile") as new_dockerfile:
        found_env = False
        for line in new_dockerfile:
            if line.strip().startswith("ENV ADDONS"):
                found_env = True
                new_docker_file_lines += new_env_lines
            if found_env:
                if not line.strip().endswith("\\"):
                    found_env = False
            else:
                new_docker_file_lines.append(line)
    with open("Dockerfile", "w") as new_dockerfile:
        new_dockerfile.writelines(new_docker_file_lines)


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
