# Copyright 2025 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path

from . import docker_compose, os_exec, ui


def create_db_from_db_dump(
    db_name: str,
    db_dump: str,
    template_db_name: str = None,
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
    if dumps := [d.name for d in Path(".").absolute().glob("*.pg") if d.is_file()]:
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
