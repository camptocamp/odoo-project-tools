# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


import re
import subprocess

import click
import jinja2

from ..utils import ui
from ..utils.misc import get_cache_path
from ..utils.path import cd


@click.group()
def cli():
    pass


@cli.command(
    help="Run a standard odoo version locally, for a customer demo or testing standard features."
)
@click.argument(
    "version",
    required=False,
    default="18.0",
    nargs=1,
)
@click.option(
    "--empty-db/--no-empty-db",
    default=True,
    help="force recreation of an empty database. Otherwise a previously created database for that version can be reused.",
)
@click.option(
    "-p",
    "--port",
    default=8080,
    help="The network port on which you will need to connect to access odoo.",
)
@click.option(
    "--force-image-pull/--no-force-image-pull",
    default=False,
    help="Force pulling updated image",
)
def run(empty_db, port, force_image_pull, version):
    # we are storing the data and the logs in ~/.cache/otools/batools/localrun-<version>
    # this enables keeping a cache of the databases through the docker composition name,
    # for instance, and having the execution logs available for examination if something crashes.
    run_dir = get_cache_path() / "batools" / f"localrun-{version}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if not re.match(r"^\d\d.\d$", version):
        ui.exit_msg("Version must be an odoo version (e.g. 17.0)")

    jinja_env = jinja2.Environment(
        loader=jinja2.PackageLoader("odoo_tools"),
    )
    template = jinja_env.get_template("localrun_docker_compose.yml.tmpl")
    dkr_compose = template.render(odoo_version=version)
    with cd(run_dir):
        with open("docker-compose.yml", "w") as fobj:
            fobj.write(dkr_compose)
        with open("docker_logs.txt", "wb") as logfile:
            ui.echo(
                f"Pulling docker image (this can be long). Logs are in {run_dir/'docker_logs.txt'}"
            )
            if force_image_pull:
                # todo: force image pulling if the docker-compose file is more than 1w old
                # (meaning there has been a new image built since the last use of the tool)
                policy = "always"
            else:
                policy = "missing"
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "pull",
                    "--quiet",
                    "--policy",
                    policy,
                    "--include-deps",
                    "odoo",
                ],
                stdout=logfile,
            )
        with open("odoo_logs.txt", "w", buffering=1) as logfile:
            ui.echo("Initializing the database")
            subprocess.run(
                ["docker", "compose", "down"]
            )  # avoid error with another Odoo running in the same port
            if empty_db:
                ui.echo("Remove previous database")
                subprocess.run(
                    [
                        "docker",
                        "compose",
                        "run",
                        "--rm",
                        "-e",
                        "MIGRATE=false",
                        "odoo",
                        "sh -c dropdb odoodb",
                    ],
                    stdout=logfile,
                    stderr=logfile,
                    text=True,
                )
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "run",
                    "--rm",
                    "-e",
                    "MIGRATE=false",
                    "odoo",
                    "odoo",
                    "--stop-after-init",
                ],
                stdout=logfile,
                stderr=logfile,
                text=True,
            )
            ui.echo("Starting Odoo")
            pipe = subprocess.Popen(
                [
                    "docker",
                    "compose",
                    "run",
                    "--rm",
                    "-q",
                    "-e",
                    "MIGRATE=false",
                    "--interactive=false",
                    "-p",
                    f"{port}:8069",
                    "odoo",
                    "odoo",
                ],
                stderr=subprocess.PIPE,
                stdout=logfile,
                bufsize=1,
                text=True,
            )
            try:
                for line in pipe.stderr:
                    logfile.write(line)
                    if "Registry loaded" in line or "Modules loaded" in line:
                        ui.echo(f"You can connect to http://localhost:{port}")
                        subprocess.Popen(["xdg-open", f"http://localhost:{port}"])
            except KeyboardInterrupt:
                ui.echo("Exiting...")
            finally:
                subprocess.run(
                    ["docker", "compose", "down"]
                )  # avoid error with another Odoo running in the same port


if __name__ == "__main__":
    cli()
