# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import PosixPath

import click

from ..utils import db, docker_compose, gh, git, ui
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
    "--template-db",
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
@click.option(
    "--keep-db",
    is_flag=True,
    default=False,
    help="keep using preexisting DBs",
)
@click.argument("pr_number")
def test(
    pr_number,
    database_dump=None,
    template_db=None,
    create_template=None,
    keep_db=False,
    port=8069,
    base_branch="master",
):
    """Test a pull request

    :param str pr_number: pull request number
    :param str database_dump: DB dump filename (within local filesystem)
    :param str template_db: template DB name (within docker DB container)
    :param bool create_template: if True, a new template DB is created
        when restoring a DB dump
    :param bool keep_db: if True, DBs are not handled by this script
    :param int port: network port on which Odoo will listen
    :param str base_branch: base branch on which the PR is based
    """
    run(docker_compose.down())
    docker_yml_name = f"docker-compose.override-{pr_number}.yml"
    db_name = _get_db_name(pr_number)
    handle_git_repository(pr_number, base_branch)
    generate_docker_yml(db_name, port, docker_yml_name)
    # No DB updates if ``--keep-db`` is used
    if not keep_db:
        template_db_name = create_template and _get_db_name(pr_number, True) or ""
        # Case 1: ``--database-dump`` is specified
        if database_dump:
            db.create_db_from_db_dump(
                db_name=db_name,
                db_dump=database_dump,
                template_db_name=template_db_name,
            )
        # Case 2: ``--template-db`` is specified
        elif template_db:
            db.create_db_from_db_template(db_name=db_name, db_template=template_db)
        # Case 3: no DB dump or DB template, check among local files
        else:
            db.create_db_from_local_files(
                db_name=db_name,
                template_db_name=template_db_name,
            )
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
        git.delete_branch(f"pr-{pr_number}")
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


def _get_db_name(pr_number, is_template: bool = False) -> str:
    return f"odoodb-{pr_number}" + ("-template" if is_template else "")
