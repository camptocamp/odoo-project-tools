# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import re
import subprocess
from datetime import datetime, timedelta

import click
import jinja2

from ..utils import docker_compose, ui
from ..utils.misc import get_cache_path
from ..utils.path import cd


def _check_docker_compose_file_is_old(dcfile) -> bool:
    dcfile_ctime = datetime.fromtimestamp(dcfile.lstat().st_ctime)
    return datetime.now() - dcfile_ctime > timedelta(weeks=1)


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
    "--force-image-pull",
    default="ask",
    required=False,
    help="Force pulling updated image",
    type=click.Choice(["yes", "no", "ask"]),
)
def run(empty_db, port, force_image_pull, version):
    # we are storing the data and the logs in ~/.cache/otools/batools/localrun-<version>
    # this enables keeping a cache of the databases through the docker composition name,
    # for instance, and having the execution logs available for examination if something crashes.
    run_dir = get_cache_path() / "batools" / f"localrun-{version}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if not re.match(r"^\d\d.\d$", version):
        ui.exit_msg("Version must be an odoo version (e.g. 17.0)")

    # Check image pull policy
    # By default, we use "missing" as pull policy; we update it to "always" in case we
    # receive ``--force-image-pull=yes``, or the docker-compose.yml file has not been
    # updated for more than 1 week and the user confirms the force pull policy
    policy = "missing"
    if force_image_pull == "yes":
        policy = "always"
    elif force_image_pull == "ask":
        docker_compose_yml = run_dir.joinpath("docker-compose.yml")
        if not docker_compose_yml.exists() or (
            _check_docker_compose_file_is_old(docker_compose_yml)
            and ui.ask_confirmation("Force-pull docker images?")
        ):
            policy = "always"

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
            subprocess.run(
                docker_compose.pull(
                    "odoo", pull_policy=policy, quiet=True, include_deps=True
                ),
                stdout=logfile,
            )
        run_environment = {"MIGRATE": "false"}
        with open("odoo_logs.txt", "w", buffering=1) as logfile:
            ui.echo("Initializing the database")
            subprocess.run(
                docker_compose.down()
            )  # avoid error with another Odoo running in the same port
            if empty_db:
                ui.echo("Remove previous database")
                subprocess.run(
                    docker_compose.run(
                        "odoo",
                        ["sh", "-c", "dropdb", "odoodb"],
                        environment=run_environment,
                    ),
                    stdout=logfile,
                    stderr=logfile,
                    text=True,
                )
            subprocess.run(
                docker_compose.run(
                    "odoo", ["odoo", "--stop-after-init"], environment=run_environment
                ),
                stdout=logfile,
                stderr=logfile,
                text=True,
            )
            ui.echo("Starting Odoo")
            pipe = subprocess.Popen(
                docker_compose.run(
                    "odoo",
                    ["odoo"],
                    quiet=True,
                    environment=run_environment,
                    interactive=False,
                    port_mapping=[(port, 8069)],
                ),
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
                        break
                for line in pipe.stderr:
                    logfile.write(line)
            except KeyboardInterrupt:
                ui.echo("Exiting...")
            finally:
                subprocess.run(docker_compose.down())


if __name__ == "__main__":
    cli()
