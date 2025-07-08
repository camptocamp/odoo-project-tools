# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import getpass
import os
import time
from contextlib import contextmanager
from datetime import datetime

import psycopg2
from invoke import task

from ..utils import ui
from ..utils.path import cd, make_dir
from ..utils.proj import get_project_manifest_key


def get_default_parameters():
    # we assume that country -> fr|ch can be used as a platform
    # some projects doesn't have country in manifest
    # to get country you can update project from odoo-template
    ctx_platform = get_project_manifest_key("country")
    assert ctx_platform, "Please specify the platform"

    # most of the project names are <single word project name>_odoo form
    # but some has <multiple words project name>_odoo
    # so to be consistent with argocd apps we construct them this way
    # TODO
    # propose a way how to handle project names
    # which won't be consistent with argocd apps
    # e.g. fleury-michon-traiteur-dedicated
    # project_name will be fleury-michon-traiteur
    # but on argocd apps we have fleury-michon-traiteur-dedicated
    project_name = get_project_manifest_key("project_name")
    ctx_customer = "-".join(project_name.split("_")[:-1])
    return ctx_platform, ctx_customer


@contextmanager
def ensure_db_container_up(ctx):
    """Ensure the DB container is up and running.

    :param ctx:
    :return: True if already up, False if it wasn't
    """
    try:
        ctx.run("docker compose port db 5432", hide=True)
        started = True
    except Exception:
        ctx.run("docker compose up -d db", hide=True)
        running = False
        # Wait for the container to start
        count = 0
        while not running:
            try:
                ctx.run("docker compose port db 5432", hide=True)
                running = True
            except Exception as e:
                count += 1
                # Raise the error after 3 failed attempts
                if count >= 3:
                    raise e
                print("Waiting for DB container to start")
                time.sleep(0.3)
        started = False
    yield
    # Stop the container if it wasn't already up and running
    if not started:
        ctx.run("docker compose stop db", hide=True)


def get_db_container_port(ctx):
    """Get and return DB container port"""
    run_res = ctx.run("docker compose port db 5432", hide=True)
    return str(int(run_res.stdout.split(":")[-1]))


def execute_db_request(ctx, dbname, sql):
    """Return the execution of given SQL request on given db"""
    result = False
    with ensure_db_container_up(ctx):
        db_port = get_db_container_port(ctx)
        dsn = f"host=localhost dbname={dbname} user=odoo password=odoo port={db_port}"
        # Connect and list DBs
        with psycopg2.connect(dsn) as db_connection:
            with db_connection.cursor() as db_cursor:
                result = db_cursor.execute(sql)
    return result


def get_db_request_result(ctx, dbname, sql):
    """Return the execution of given SQL request on given db"""
    result = False
    with ensure_db_container_up(ctx):
        db_port = get_db_container_port(ctx)
        dsn = f"host=localhost dbname={dbname} user=odoo password=odoo port={db_port}"
        # Connect and list DBs
        with psycopg2.connect(dsn) as db_connection:
            with db_connection.cursor() as db_cursor:
                db_cursor.execute(sql)
                result = db_cursor.fetchall()
    return result


def get_db_list(ctx):
    """Return the list of db on container"""
    sql = """
        SELECT datname
        FROM pg_database
        WHERE datistemplate = false
        AND datname not in ('postgres', 'odoo');
    """
    databases_fetch = get_db_request_result(ctx, "postgres", sql) or []
    return [db_name_tuple[0] for db_name_tuple in databases_fetch]


def expand_path(path):
    if path.startswith("~"):
        path = os.path.expanduser(path)
    return path


@task(name="list-versions")
def list_versions(ctx):
    """Print a table of DBs with Marabunta version and install date."""
    res = {}
    sql = """
        SELECT date_done, number
        FROM marabunta_version
        ORDER BY date_done DESC
        LIMIT 1;
    """
    # Get version for each DB
    db_list = get_db_list(ctx)
    for db_name in db_list:
        try:
            version_fetch = get_db_request_result(ctx, db_name, sql)
            version_tuple = version_fetch[0]
        except psycopg2.ProgrammingError:
            # Error expected when marabunta_version table does not exist
            version_tuple = (None, "unknown")
        res[db_name] = version_tuple

    size1 = max([len(x) for x in res.keys()]) + 1
    size2 = max([len(x[1]) for x in res.values()]) + 1
    size3 = 10  # len("2018-01-01")
    cols = (("DB Name", size1), ("Version", size2), ("Install date", size3))
    thead = ""
    line_width = 4  # spaces
    for col_name, col_size in cols:
        thead += "{:<{size}}".format(col_name, size=col_size + 1)
        line_width += col_size
    print(thead)
    print("=" * line_width)
    for db_name, version in sorted(
        res.items(), key=lambda x: x[1][0] or datetime.min, reverse=True
    ):
        if version[0]:
            time = version[0].strftime("%Y-%m-%d")
        else:
            time = "unknown"
        print(
            "{:<{size1}} {:<{size2}} {:<12}".format(
                db_name, version[1], time, size1=size1, size2=size2
            )
        )


@task(name="download-dump")
def download_dump(ctx, platform="", customer="", env="int", dump_name="", dumpdir="."):
    """Download Dump

    Works only with Azure and celebrimbor_cli

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    :param dump_name: dump name, you can get from task=list-of-dumps or task=generate-dump
    :param dumpdir: Location of Dump directory
    :return: Decrypted Dump on the dumpdir
    """
    ctx_platform, ctx_customer = get_default_parameters()
    p_platform = platform if platform else ctx_platform
    p_customer = customer if customer else ctx_customer
    # Get name of dump in azure list of dump
    try:
        database_name = (
            dump_name or _get_list_of_dumps(ctx, p_platform, p_customer, env)[-1]
        )  # get the last
    except IndexError:
        ui.exit_msg(f"Dump not found for {p_customer} on {p_platform} {env}")

    # gpg_fname is like fighting_snail_1024[...].pg.gpg
    gpg_fname = os.path.basename(database_name)
    # fname is like fighting_snail_1024[...].pg
    fname = os.path.splitext(gpg_fname)[0]
    make_dir(dumpdir)
    with cd(dumpdir):
        if not os.path.isfile(fname):
            print(f"Azure Downloading dump...{database_name}")
            print(f"From: {p_platform} {env} of {p_customer}")
            print(f"to: {os.getcwd()}")
            _download_from_azure(ctx, p_platform, p_customer, env, database_name)
        else:
            print(f"A file named {fname} already exists, skipping download.")
    return fname


@task(name="generate-dump")
def generate_dump(ctx, platform="", customer="", env="int"):
    """Generate Dump

    Works only with Azure and celebrimbor_cli

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    :return: dump name
    """
    ctx_platform, ctx_customer = get_default_parameters()
    p_platform = platform if platform else ctx_platform
    p_customer = customer if customer else ctx_customer
    generate = ctx.run(
        f"celebrimbor_cli -p {p_platform} dump -c {p_customer} -e {env} -r",
        hide=True,
    )
    dump_name = eval(generate.stdout)["name"]
    print(f"{dump_name} is generated for {p_customer} on {p_platform} {env}")
    return dump_name


@task(name="upload-dump")
def upload_dump(ctx, db_path, platform="", customer="", env="int"):
    """Upload dump

    Works only with Azure and celebrimbor_cli

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    :param db_path: Path of *.pg dump file
    :return: dump name
    """
    ctx_platform, ctx_customer = get_default_parameters()
    p_platform = platform if platform else ctx_platform
    p_customer = customer if customer else ctx_customer
    dump_file_path = expand_path(db_path)
    ctx.run(
        f"celebrimbor_cli -p {p_platform} dump -c {p_customer} -e {env} -i {dump_file_path}"
    )
    print(f"{dump_file_path} is uploaded for {p_customer} on {p_platform} {env}")


@task(name="restore-from-prod")
def restore_from_prod(ctx, platform="", customer="", env="int"):
    """Initiate a replication from the prod environment

    Works only with Azure and celebrimbor_cli

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    """
    ctx_platform, ctx_customer = get_default_parameters()
    p_platform = platform if platform else ctx_platform
    p_customer = customer if customer else ctx_customer
    ctx.run(
        f"celebrimbor_cli -p {p_platform} restore -c {p_customer} -e {env} --from-prod"
    )
    print(f"Replica from prod is restored for {p_customer} on {p_platform} {env}")


@task(name="azure-restore-dump")
def azure_restore_dump(ctx, dump_name, platform="", customer="", env="int"):
    """Restore uploaded dump

    Works only with Azure and celebrimbor_cli

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    :param dump_name: dump name, you can get from task=list-of-dumps or task=generate-dump
    """
    ctx_platform, ctx_customer = get_default_parameters()
    p_platform = platform if platform else ctx_platform
    p_customer = customer if customer else ctx_customer
    ctx.run(
        f"celebrimbor_cli -p {p_platform} restore -c {p_customer} -e {env} -n {dump_name}"
    )
    print(f"{dump_name} is restored for {p_customer} on {p_platform} {env}")


@task(name="restore-dump")
def restore_dump(ctx, dump_path, db_name="", hide_traceback=True):
    """Restore a PG Dump for given database name.

    :param dump_path: Local path to the dump
    :param db_name: Name of the Database to restore upon.
    If none specified a new on w/ the same name of the original one + date
    will be created.
    """
    if not db_name:
        # ie: polished_morning_3582-20181114-031713
        db_name = os.path.splitext(os.path.basename(dump_path))[0]
    # rely on PG error if database already exists
    ctx.run(f"docker compose run --rm odoo createdb -O odoo {db_name}")
    print("Restoring", dump_path, "on", db_name)
    ctx.run(
        "docker compose run --rm odoo pg_restore -O "
        f"-d {db_name} < {expand_path(dump_path)}",
        hide=hide_traceback,
    )
    print("Dump successfully restored on", db_name)
    if db_name != "odoodb":
        # print shortcut to run this new db
        print("You can Odoo on this DB:")
        print(
            f"docker compose run --rm -e DB_NAME={db_name} "
            "-p 8069:8069 odoo odoo --workers=0"
        )


@task(name="download-restore-dump")
def download_restore_dump(
    ctx,
    platform="",
    customer="",
    env="int",
    dump_name="",
    dumpdir=".",
    restore_db="",
):
    """A combo of the above tasks.

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    :param dump_name: dump name, you can get from task=list-of-dumps or task=generate-dump
    :param dumpdir: Location of Dump directory
    :param restore_db: Name of the Database to restore upon
    In `download_dump` defaults to dump name.
    """
    ctx_platform, ctx_customer = get_default_parameters()
    p_platform = platform if platform else ctx_platform
    p_customer = customer if customer else ctx_customer
    dump_path = download_dump(
        ctx, p_platform, p_customer, env, dump_name, dumpdir=dumpdir
    )
    restore_dump(ctx, dump_path, db_name=restore_db)


@task(name="local-dump")
def local_dump(ctx, db_name="odoodb", path="."):
    """Create a PG Dump for given database name.

    :param db_name: Name of the Database to dump
    :param path: Local path to store the dump
    :return: Dump file path
    """
    path = expand_path(path)
    with ensure_db_container_up(ctx):
        db_port = get_db_container_port(ctx)
        username = getpass.getuser()
        project_name = get_project_manifest_key("project_name")
        dump_name = "{}_{}-{}.pg".format(
            username, project_name, datetime.now().strftime("%Y%m%d-%H%M%S")
        )
        dump_file_path = f"{path}/{dump_name}"
        ctx.run(
            f"pg_dump -h localhost -p {db_port} --format=c -U odoo --file {dump_file_path} {db_name}",
            hide=True,
        )
        print(f"Dump successfully generated at {dump_file_path}")
    return dump_file_path


@task(name="dump-and-share")
def dump_and_share(
    ctx,
    platform="",
    customer="",
    env="int",
    db_name="odoodb",
    tmp_path="/tmp",
    keep_local_dump=False,
):
    """Create a dump and share it on Azure.

    Usage : invoke database.dump-and-share --db-name=mydb

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    :param db_name: Name of the Database to dump
    :param tmp_path: Temporary local path to store the dump
    :param keep_local_dump: Boolean to keep the generated and encrypted dumps
    locally
    """
    ctx_platform, ctx_customer = get_default_parameters()
    p_platform = platform if platform else ctx_platform
    p_customer = customer if customer else ctx_customer
    tmp_path = expand_path(tmp_path)
    dump_file_path = local_dump(ctx, db_name=db_name, path=tmp_path)
    upload_dump(ctx, dump_file_path, p_platform, p_customer, env)
    if not keep_local_dump:
        ctx.run(f"rm {dump_file_path}")


def _download_from_azure(ctx, platform, customer, env, dump_name):
    """Download one dump from Azure with celebrimbor_cli.

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    :param dump_name: dump name, you can get from task=list-of-dumps or task=generate-dump
    """
    ctx.run(
        f"celebrimbor_cli -p {platform} download -c {customer} -e {env} --name {dump_name}"
    )


def _get_list_of_dumps(ctx, platform, customer, env):
    """Retrieve list of dumps from Azure with celebrimbor_cli.

    :param platform: platform you want to run the command on
    :param customer: customer name (or project name depending on the context)
    :param env: environment (can be prod, int or labs.<lab-name>)
    :return: a list of all dumps matching the params.
    """
    res = []
    result_of_azure_call = ctx.run(
        f"celebrimbor_cli -p {platform} list -c {customer} -e {env} -r",
        hide=True,
    )
    result_of_azure_call = eval(result_of_azure_call.stdout)
    for fname in result_of_azure_call or []:
        res.append(fname["name"])
    return res


@task(name="list-of-dumps")
def list_of_dumps(ctx, platform="", customer="", env="int"):
    ctx_platform, ctx_customer = get_default_parameters()
    p_platform = platform if platform else ctx_platform
    p_customer = customer if customer else ctx_customer
    dumps = _get_list_of_dumps(ctx, p_platform, p_customer, env)
    if not dumps:
        print("No dump found")
        return
    for fname in dumps:
        print(fname)
