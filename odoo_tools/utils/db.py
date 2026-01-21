# Copyright 2025 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import atexit
import getpass
import tempfile
from contextlib import contextmanager
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import Literal

import psycopg2

from . import docker_compose, os_exec, proj, ui


def create_db_from_db_dump(
    db_name: str,
    db_dump: PathLike | str,
    template_db_name: str | None = None,
):
    """Restores a DB dump, optionally creates a DB template

    :param str db_name: name of the DB to create
    :param str db_dump: filename of the DB dump to restore
    :param str template_db_name: if set, a new template DB of the given name is created
    """
    if template_db_name:
        _handle_database_template(template_db_name, db_dump)
        _restore_database_from_template(db_name, template_db_name)
    else:
        _load_database(db_name, db_dump)


def create_db_from_db_template(db_name: str, db_template: str):
    """Creates a new DB from the given template

    :param str db_name: name of the DB to create
    :param str db_template: the name of the template DB to use
    """
    _restore_database_from_template(db_name, db_template)


def create_db_from_local_files(
    db_name: str,
    template_db_name: str = None,
):
    """Checks current directory for ``.pg`` files and tries to restore one of them

    :param str db_name: name of the DB to create
    :param str template_db_name: if set, a new template DB of the given name is created
    """
    if dumps := [d.name for d in Path().absolute().glob("*.pg") if d.is_file()]:
        dumps.sort()  # Sort alphabetically to make it easier to read for users
        choices = dict(enumerate(dumps, start=1))
        ui.echo(
            "Found the following DB dumps:\n"
            + "\n".join(f"{i} - {n}" for i, n in choices.items())
        )
        key = ui.ask_question("Enter the number of the DB dump to restore", type=int)
        if db_dump := choices.get(key):
            create_db_from_db_dump(db_name, db_dump, template_db_name)
        else:
            ui.exit_msg(
                f"Invalid selection: {key} not found in {', '.join(map(str, choices))}"
            )
    else:
        ui.exit_msg("No database dump found")


def dump_db(db_name: str, output_path: PathLike = ".", format: Literal["c", "p"] = "c"):
    """Dump a database to a file"""
    output_path = Path(output_path)
    # If output_path is a directory, generate a filename
    if output_path.is_dir() or output_path.as_posix().endswith("/"):
        username = getpass.getuser()
        project_name = proj.get_project_manifest_key("project_name")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{username}_{project_name}-{timestamp}.pg"
        output_path = output_path / filename
    # Make sure the target directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Create a temporary directory to mount onto the container as volume
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Dump it
        local_volume_path = Path(tmp_dir)
        local_dump_path = local_volume_path / output_path.name
        container_volume_path = Path("/tmp/otools_db")
        container_dump_path = container_volume_path / output_path.name
        command = docker_compose.run(
            "odoo",
            [
                "pg_dump",
                "--format",
                format,
                "--file",
                str(container_dump_path),
                db_name,
            ],
            tty=True,
            quiet=True,
            volumes=[(local_volume_path, container_volume_path)],
        )
        os_exec.run(command, check=True)
        os_exec.run(f"mv {local_dump_path} {output_path}", check=True)
    ui.echo(f"Dump successfully generated at {output_path}")
    return output_path


def _handle_database_template(template_db_name, database_dump):
    # at this point we should have the database loaded under proper name
    os_exec.run(docker_compose.drop_db(template_db_name))
    os_exec.run(docker_compose.create_db(template_db_name))
    try:
        ui.echo(f"🥡 Creating template {template_db_name} from dump {database_dump}")
        docker_compose.run_restore_db(template_db_name, database_dump)
    except Exception:
        # to ignore warnings on db restore
        pass


def _restore_database_from_template(db_name, template):
    ui.echo(f"🥡 Restore database {db_name} from template {template}")
    os_exec.run(docker_compose.drop_db(db_name))
    os_exec.run(docker_compose.restore_db_from_template(db_name, template))


def _load_database(db_name, fname):
    os_exec.run(docker_compose.drop_db(db_name))
    os_exec.run(docker_compose.create_db(db_name))

    if Path(fname).is_file():
        try:
            ui.echo(f"🥡 Restoring database {db_name} from dump {fname}")
            docker_compose.run_restore_db(db_name, fname)
        except Exception:
            pass
    else:
        msg = f"❌ ** Database file {fname} for restore was not found**"
        return ui.exit_msg(msg)
    return fname


@contextmanager
def ensure_db_container_up():
    """Ensure the database container is up and running.

    Yields:
        int: the port of the database container
    """
    try:
        # First, try to get the port of the database container.
        # If we succeed, then it means it's already running.
        port = get_db_port()
    except Exception:
        # Register a function to be called when the program exits, to stop the
        # database container. This way we don't have to start/stop the container
        # multiple times during the execution of the program.
        atexit.register(os_exec.run, docker_compose.down(service="db"))
        # Start the database container
        os_exec.run(docker_compose.up(service="db", detach=True, wait=True))
        port = get_db_port()
    yield port


def get_db_port() -> int:
    """Get and return database container port."""
    result = os_exec.run(docker_compose.get_db_port(), check=True)
    return int(result.split(":")[-1])


def execute_db_request(dbname: str, sql: str) -> list[tuple]:
    """Execute a SQL request on the given database."""
    with ensure_db_container_up() as db_port:
        dsn = f"host=localhost dbname={dbname} user=odoo password=odoo port={db_port}"
        with psycopg2.connect(dsn) as db_connection:
            with db_connection.cursor() as db_cursor:
                db_cursor.execute(sql)
                return db_cursor.fetchall()


def get_db_list() -> list[str]:
    """Return the list of databases on container."""
    sql = """
        SELECT datname
        FROM pg_database
        WHERE datistemplate = false
        AND datname not in ('postgres', 'odoo');
    """
    return [row[0] for row in execute_db_request("postgres", sql)]
