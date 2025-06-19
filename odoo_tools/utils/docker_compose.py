# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""
Helper functions to get docker compose commands to run, handling the different
command line options found in different versions of docker compose.
"""

from . import os_exec


def get_version():
    version = os_exec.run("docker compose version --short")
    return [int(x) for x in version.split(".")]


def run(
    service,
    cmd,
    environment,
    remove=True,
    quiet=True,
    interactive=True,
    port_mapping=None,
):
    version = get_version()
    command = ["docker", "compose", "run"]
    if remove:
        command.append("--rm")
    if not interactive:
        command.append("--interactive=false")
    for key, value in environment.items():
        command += ["-e", f"{key}={value}"]
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


def down():
    command = ["docker", "compose", "down"]
    return command
