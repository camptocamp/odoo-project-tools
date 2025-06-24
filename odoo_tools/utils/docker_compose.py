# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""
Helper functions to get docker compose commands to run, handling the different
command line options found in different versions of docker compose.
"""

import subprocess

from . import os_exec


def get_version():
    version = os_exec.run("docker compose version --short")
    return [int(x) for x in version.split(".")]


def up(override=None):
    command = ["docker", "compose", "up"]
    if override:
        command[2:2] = ["-f", "docker-compose.yml", "-f", override]
    return command


def run(
    service,
    cmd,
    environment=None,
    remove=True,
    quiet=True,
    interactive=True,
    port_mapping=None,
    override=None,
    tty=False,
):
    version = get_version()
    command = ["docker", "compose", "run"]
    if environment is None:
        environment = {}
    if override:
        command[2:2] = ["-f", "docker-compose.yml", "-f", override]
    if remove:
        command.append("--rm")
    if not interactive:
        command.append("--interactive=false")
    for key, value in environment.items():
        command += ["-e", f"{key}={value}"]
    if tty:
        command.append("-T")
    if quiet:
        if version >= [2, 35, 0]:
            command.append("--quiet")
        else:
            command.append("--quiet-pull")
    if port_mapping:
        for external_port, internal_port in port_mapping:
            command += ["--publish", f"{external_port}:{internal_port}"]
    command.append(service)
    if isinstance(cmd, str):
        cmd = [cmd]
    command += cmd
    return command


def pull(service, quiet=True, pull_policy="missing", include_deps=False):
    command = ["docker", "compose", "pull", "--policy", pull_policy]
    if quiet:
        command.append("--quiet")
    if include_deps:
        command.append("--include-deps")
    command.append(service)
    return command


def build(service="odoo", quiet=True):
    command = ["docker", "compose", "build"]
    if quiet:
        command.append("--quiet")
    command.append(service)
    return command


def down():
    command = ["docker", "compose", "down"]
    return command


def drop_db(database_name):
    command = run("odoo", ["dropdb", database_name], quiet=True)
    return command


def create_db(database_name):
    command = run("odoo", ["createdb", "-O", "odoo", database_name], quiet=True)
    return command


def restore_db(database_name):
    command = run("odoo", ["pg_restore", "-Oxd", database_name], tty=True, quiet=True)
    return command


def restore_db_from_template(database_name, template_name):
    command = run("odoo", ["createdb", "-T", template_name, database_name], quiet=True)
    return command


def run_restore_db(database_name, db_dump):
    popen = subprocess.Popen(
        restore_db(database_name), stdin=open(db_dump, "rb"), bufsize=1024**3
    )
    popen.communicate()
