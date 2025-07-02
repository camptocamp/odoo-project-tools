# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import PosixPath

import click

from ..utils import docker_compose, gh, git, ui
from ..utils.os_exec import run
from ..utils.path import cd, root_path


@click.group()
def cli():
    pass


# TODO: this command ATM is kind of a mix between `add` and `add-pending`.
# As we won't use yet pip installed modules.


@cli.command()
@click.option(
    "-f", "--database-dump", help="filename containing a downloaded database dump"
)
@click.option(
    "--create-template/--no-create-template",
    default=False,
    help="create a template database for faster restores in the future.",
)
@click.option(
    "-t",
    "--template_db",
    help="the name of a template database to use for restoring the project's database",
)
@click.option(
    "-b",
    "--base-branch",
    default="master",
    help="the base branch on which the PR is based",
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=8069,
    help="the network port on which Odoo will listen",
)
@click.argument("pr_number")
def test(
    pr_number,
    database_dump=None,
    # get_remote_db=None,
    template_db=None,
    create_template=None,
    port=8069,
    base_branch="master",
):
    """test a pull request on a restored database dump"""
    run(docker_compose.down())
    docker_yml_name = f"docker-compose.override-{pr_number}.yml"
    dbname = f"odoodb-{pr_number}"
    template_db_name = _template_db_name(pr_number)
    handle_git_repository(pr_number, base_branch)
    generate_docker_yml(dbname, port, docker_yml_name)
    if database_dump:
        fname = database_dump

        if create_template:
            _handle_database_template(template_db_name, database_dump)
            _restore_database_from_template(dbname, template_db_name)
        else:
            _load_database(dbname, fname)
    else:
        if template_db:
            template_db_name = template_db
        else:
            # assume the template db was previously created for this PR
            template_db_name = _template_db_name(pr_number)
        _restore_database_from_template(dbname, template_db_name)

    ui.echo("Starting container")
    ui.echo(
        "✨ Database migration started you can reach database on http://localhost:8069"
    )
    run(docker_compose.up(override=docker_yml_name))


@cli.command()
@click.argument("pr_number")
@click.option(
    "-b",
    "--base-branch",
    default="master",
    help="the base branch on which the PR is based",
)
def checkout(pr_number, base_branch):
    handle_git_repository(pr_number, base_branch)


@cli.command()
@click.argument("pr_number")
def clean(pr_number):
    """clean the branch and database created by otools-pr test"""
    ui.echo("🛁 Removing branch")
    try:
        git.checkout("master")
        git.delete_branch(pr_number)
    except Exception as exc:
        ui.echo(f"Error while trying to remove branch: {exc}")
    ui.echo("🛁 Removing database")
    dbname = f"odoodb-{pr_number}"

    run(docker_compose.down())
    run(docker_compose.drop_db(dbname))


def handle_git_repository(pr_number, branch):
    gh.check_git_diff()
    master = f"remotes/origin/{branch}"

    with cd(root_path()):
        try:
            ui.echo("Fetching source code")
            run(f"git switch -c pr-{pr_number}")
        except Exception:
            run(f"git switch pr-{pr_number}")
        run(f"git fetch origin +refs/pull/{pr_number}/merge")
        run("git reset --hard FETCH_HEAD")

        dockerfile = PosixPath("Dockerfile")
        if not dockerfile.is_file():
            # old layout
            dockerfile = PosixPath("Dockerfile")
        requirements = PosixPath("odoo/requirements.txt")
        if not requirements.is_file():
            # old layout
            requirements = PosixPath("odoo/requirements.txt")

        docker_diff = run(f"git diff pr-{pr_number} {master} -- {dockerfile}")
        req_diff = run(f"git diff pr-{pr_number} {master} -- {requirements}")

        for submodule in git.iter_gitmodules():
            git.submodule_init(submodule)
            git.submodule_sync(submodule.path)
            git.submodule_update(submodule.path)
        if docker_diff or req_diff:
            ui.echo("👷 Rebuilding docker image")
            run(docker_compose.build())


def generate_docker_yml(dbname, port, file_name):
    # generate additional docker-compose file
    with open(file_name, "w+") as f:
        data = f"""
services:
  odoo:
    environment:
        DB_NAME: {dbname}
        MARABUNTA_MODE: full
  nginx:
    ports:
      - {port}:80
        """
        f.write(data)


def _load_database(db_name, fname):
    run(docker_compose.drop_db(db_name))
    run(docker_compose.create_db(db_name))

    if PosixPath(fname).is_file():
        try:
            ui.echo(f"🥡 Restoring database {db_name} from dump {fname}")
            docker_compose.run_restore_db(db_name, fname)
        except Exception:
            pass
    else:
        msg = f"❌ ** Database file {fname} for restore was not found**"
        ui.exit_msg(msg)
        return
    return fname


def _template_db_name(pr_number):
    return f"odoodb{pr_number}-template"


def _handle_database_template(template_db_name, database_dump):
    # at this point we should have the database loaded under proper name
    run(docker_compose.drop_db(template_db_name))
    run(docker_compose.create_db(template_db_name))
    try:
        ui.echo(f"🥡 Creating template {template_db_name} from dump {database_dump}")
        docker_compose.run_restore_db(template_db_name, database_dump)
    except Exception:
        # to ignore warnings on db restore
        pass


def _restore_database_from_template(db_name, template):
    ui.echo(f"🥡 Restore database {db_name} from template {template}")
    run(docker_compose.drop_db(db_name))
    run(docker_compose.restore_db_from_template(db_name, template))
