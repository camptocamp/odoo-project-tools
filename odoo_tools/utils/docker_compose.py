# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""
Helper functions to get docker compose commands to run, handling the different
command line options found in different versions of docker compose.
"""

from __future__ import annotations

import subprocess
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from . import misc, os_exec

if TYPE_CHECKING:
    from configparser import ConfigParser


def get_version():
    version = os_exec.run("docker compose version --short")
    return [int(x) for x in version.split(".") if x.isdigit()]


def up(override=None, detach=False, wait=True, service=None):
    command = ["docker", "compose", "up"]
    if override:
        command[2:2] = ["-f", "docker-compose.yml", "-f", override]
    if detach:
        command.append("--detach")
        if wait:
            command.append("--wait")
    if service:
        command.append(service)
    return command


def run(
    service,
    cmd,
    environment=None,
    remove=True,
    quiet=True,
    interactive=True,
    port_mapping=None,
    volumes=None,
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
    if volumes is not None:
        for host_path, container_path in volumes:
            command += ["-v", f"{host_path}:{container_path}"]
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


def down(service=None):
    command = ["docker", "compose", "down"]
    if service:
        command.append(service)
    return command


def port(service, port):
    command = ["docker", "compose", "port", service, port]
    return command


def get_db_port():
    command = port("db", "5432")
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


def run_restore_db(
    database_name, db_dump: PathLike | str, format: Literal["sql", "dump"] = "dump"
):
    with Path(db_dump).open("rb") as fdump:
        if format == "sql":
            command = run("odoo", ["psql", "-d", database_name], tty=True, quiet=True)
        else:
            command = restore_db(database_name)
        # Execute
        popen = subprocess.Popen(command, stdin=fdump, bufsize=1024**3)
        popen.communicate()


def run_printenv(service="odoo") -> dict[str, str]:
    """Returns the environment variables of a given service container"""
    output = os_exec.run(run(service, ["printenv"]))
    variables = {}
    for line in output.splitlines():
        try:
            name, value = line.strip().split("=", maxsplit=1)
        except ValueError:
            # not formatted as an environment variable, we can ignore
            continue
        variables[name] = value
    return variables


def read_odoo_cfg(service="odoo") -> ConfigParser:
    """Returns a parsed odoo.cfg file read from the given service container"""
    marker = "========== odoo.cfg =========="
    content = os_exec.run(
        run(service, ["sh", "-c", f"echo '{marker}' && cat $ODOO_RC"])
    )
    content = content.split(marker)[1]
    return misc.parse_ini_cfg(content, "options")
