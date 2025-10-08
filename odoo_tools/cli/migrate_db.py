"""Helper to launch all the migration steps locally.

Download the production dump:

    $ celebrimbor_cli -p ch download -c CUSTOMER -e prod

Launch the migration locally (warning: ensure your migration project folder
is up-to-date and built):

    $ otools-migrate-db /path/to/prod_dump.pg


The migration is composed of the following steps:

    - pre_migrate_restore_prod  Restore downloaded production dump
    - pre_migrate_fix_prod_data Fix/update the production DB
    - pre_migrate_dump_prod     Dump the fixed production DB before sending it to Odoo S.A.
    - migrate_odoo              Upgrade production DB thanks to upgrade.odoo.com
    - restore_odoo_migrated     Restore 'dump.sql' in PostgreSQL
    - dump_odoo_migrated        Dump Odoo S.A. migrated DB in a Pg logical format (.pg)
    - migrate_c2c_{step}        Run C2C migration scripts on Odoo S.A. migrated DB
    - dump_c2c_migrated         Dump C2C migrated DB
"""

import os
import pathlib
import shutil
import subprocess
import zipfile
from datetime import datetime
from urllib.request import urlretrieve

import click
import psycopg2

from ..utils.path import build_path, root_path
from ..utils.proj import get_current_version

ODOO_UPGRADE_SCRIPT = "https://upgrade.odoo.com/upgrade"


def dt():
    return datetime.now().strftime("%F %T")


@click.command()
@click.argument(
    "prod_dump_path",
    required=True,
)
@click.option(
    "--contract-number",
    "-c",
    help=(
        "The contract number associated to the database. "
        "If not set, it will be retrieved from the production database."
    ),
)
@click.option(
    "--store-path",
    "-s",
    help=(
        "Folder path where migration files (dumps, logs...) will be stored. "
        "If not set, the project root folder will be used."
    ),
)
@click.option(
    "--restart",
    is_flag=True,
    help="Restart the whole migration from production dump (Odoo S.A. + C2C).",
)
@click.option(
    "--restart-c2c",
    is_flag=True,
    help="Restart C2C migration from Odoo S.A. migrated database.",
)
@click.option(
    "--restart-c2c-external",
    is_flag=True,
    help="Restart the C2C migration from the 'core' snapshot.",
)
@click.option(
    "--restart-c2c-local",
    is_flag=True,
    help="Restart the C2C migration from the 'external' snapshot.",
)
@click.option(
    "--restart-c2c-cleanup",
    is_flag=True,
    help="Restart the C2C migration from the 'local' snapshot.",
)
@click.option(
    "--no-db-snapshot",
    is_flag=True,
    help="Do not generate database snapshots after each migration step.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    prod_dump_path: str,
    contract_number: str,
    store_path: str,
    restart: bool,
    restart_c2c: bool,
    restart_c2c_external: bool,
    restart_c2c_local: bool,
    restart_c2c_cleanup: bool,
    no_db_snapshot: bool,
):
    """Run a full database migration (Odoo S.A. + C2C).

    E.g.:

    otools-migrate-db run /path/to/mig_project_odoo ~/path/to/prod_dump.pg
    """
    ctx.ensure_object(dict)
    _check_migration_project()
    _prepare_parameters()
    _ensure_db_container_is_up()
    # Run migration steps
    steps = [
        pre_migrate_restore_prod,
        pre_migrate_fix_prod_data,
        pre_migrate_dump_prod,
        migrate_odoo,
        restore_odoo_migrated,
        dump_odoo_migrated,
        migrate_c2c_core,
        migrate_c2c_external,
        migrate_c2c_local,
        migrate_c2c_cleanup,
        dump_c2c_migrated,
        migration_done,
    ]
    for i, step in enumerate(steps, start=1):
        title = f"{i:>2} - {step.__name__}..."
        print(f"{dt()}: {title:<40}", end="", flush=True)
        start = datetime.now()
        is_done = step()
        # print elapsed time, e.g. '+00:10:40' if step has been processed
        if is_done:
            end = datetime.now()
            elapsed = end - start
            elapsed_str = " +" + str(elapsed).split(".")[0]
            print(elapsed_str)
        else:
            print()


@click.pass_context
def _check_migration_project(ctx):
    """Check that current project is able to run a database migration."""
    migration_dir = build_path("odoo/songs/migration_db")
    if not migration_dir.exists():
        raise SystemExit(f"{root_path()} is not a migration project. Abort.")


@click.pass_context
def _prepare_parameters(ctx):
    prod_dump_path = pathlib.Path(ctx.params["prod_dump_path"])
    ctx.obj["target_version"] = get_current_version()[:4]
    ctx.obj["project_path"] = root_path()
    store_path = root_path()
    if ctx.params["store_path"]:
        store_path = pathlib.Path(ctx.params["store_path"])
        if not store_path.exists():
            raise SystemExit(f"{store_path} doesn't exist")
    ctx.obj["store_path"] = store_path
    ctx.obj["container_store_path"] = pathlib.Path("/migrate-db-volume")
    ctx.obj["input_db_path"] = prod_dump_path.expanduser().absolute()
    ctx.obj["input_db_file"] = prod_dump_path.name
    ctx.obj["pre_migration_sql_path"] = "odoo/songs/migration_db/pre-migration.sql"
    ctx.obj["odoo_upgrade_env_path"] = build_path(
        "odoo/songs/migration_db/odoo_upgrade_env_file"
    )
    ctx.obj["db_name"] = prod_dump_path.stem
    ctx.obj["db_prod"] = ctx.obj["db_name"] + "_prod"
    ctx.obj["db_prod_fixed"] = ctx.obj["db_name"] + "_prod_fixed"
    ctx.obj["db_odoo_migrated"] = ctx.obj["db_name"] + "_odoo_migrated"
    ctx.obj["db_c2c_core"] = ctx.obj["db_name"] + "_core"
    ctx.obj["db_c2c_external"] = ctx.obj["db_name"] + "_external"
    ctx.obj["db_c2c_local"] = ctx.obj["db_name"] + "_local"
    ctx.obj["db_c2c_cleanup"] = ctx.obj["db_name"] + "_cleanup"
    ctx.obj["db_c2c_migrated"] = ctx.obj["db_name"] + "_c2c_migrated"
    ctx.obj["contract_number"] = ctx.params["contract_number"]


@click.pass_context
def pre_migrate_restore_prod(ctx):
    is_done = False
    db_path = ctx.obj["input_db_path"]
    db_name = ctx.obj["db_prod"]
    if not _db_exists(db_name):
        _dropdb(db_name)
        _createdb(db_name)
        try:
            _run_docker_compose_cmd(
                f"run -T --rm odoo pg_restore -x -O -d {db_name} < {db_path}"
            )
        except subprocess.CalledProcessError:
            print("💥")
            raise
        print("✅", end="")
        is_done = True
    else:
        print("ℹ️  (skipped: prod database already restored)", end="")
    # Retrieve Odoo Contract Number from prod database
    if not ctx.obj["contract_number"]:
        res = _execute_db_request(
            db_name,
            "SELECT value FROM ir_config_parameter WHERE key='database.enterprise_code';",
        )
        if res:
            contract_number = res[0][0]
            ctx.obj["contract_number"] = contract_number
        if not ctx.obj["contract_number"]:
            raise SystemExit(
                "\nUnable to retrieve the Odoo Contract Number from prod database. "
                "Please provide it with --contract-number / -c parameter."
            )
    return is_done


@click.pass_context
def pre_migrate_fix_prod_data(ctx):
    is_done = False
    db_prod = ctx.obj["db_prod"]
    db_prod_fixed = ctx.obj["db_prod_fixed"]
    script_path = build_path(ctx.obj["pre_migration_sql_path"])
    container_script_path = "/" + ctx.obj["pre_migration_sql_path"]
    if script_path.exists():
        if not _db_exists(db_prod_fixed) or ctx.params["restart"]:
            # Fixed prod db doesn't exist or restart enabled => create it
            _dropdb(db_prod_fixed)
            _createdb(db_prod_fixed, db_template=db_prod)
            try:
                _run_docker_compose_cmd(
                    f"run -T --rm odoo psql -d {db_prod_fixed} "
                    f"-f {container_script_path}"
                )
            except subprocess.CalledProcessError:
                print("💥")
                raise
            print("✅", end="")
            is_done = True
        else:
            print("ℹ️  (skipped: fixed production database already exists)", end="")
        return is_done
    print("ℹ️  (skipped: no pre-migration.sql script to run)", end="")
    # Force the fixed DB name to current one if there is no pre-migration script
    ctx.obj["db_prod_fixed"] = ctx.obj["db_prod"]
    return is_done


@click.pass_context
def pre_migrate_dump_prod(ctx):
    is_done = False
    db_name = ctx.obj["db_prod_fixed"]
    dump_path = _get_db_prod_fixed_dump_path()
    if ctx.params["restart"] and dump_path.exists():
        dump_path.unlink()
    if dump_path.exists():
        print("ℹ️  (skipped: production database dump already exists)", end="")
        return is_done
    script_path = build_path(ctx.obj["pre_migration_sql_path"])
    if not script_path.exists():
        # No pre-migration.sql script means we don't need to dump the fixed
        # production database (could be long depending on the DB size).
        # A simple copy of the .pg file to .dump is enough to satisfy
        # Odoo S.A. upgrade script.
        shutil.copy(ctx.obj["input_db_path"], dump_path)
        print("✅", end="")
        is_done = True
        return is_done
    container_dump_path = _get_db_prod_fixed_dump_path(in_container=True)
    mount_opts = f"-v {ctx.obj['store_path']}:/{ctx.obj['container_store_path']}"
    try:
        _run_docker_compose_cmd(
            f"run {mount_opts} --rm odoo pg_dump -b -Fc -d {db_name} "
            f"-f {container_dump_path}"
        )
    except subprocess.CalledProcessError:
        print("💥")
        raise
    print("✅", end="")
    return True


@click.pass_context
def migrate_odoo(ctx):
    upgraded_zip_path = ctx.obj["store_path"].joinpath("upgraded.zip")
    if ctx.params["restart"] and upgraded_zip_path.exists():
        upgraded_zip_path.unlink()
    if upgraded_zip_path.exists():
        print("ℹ️  (skipped: upgraded.zip file already exists)", end="")
        return False
    prod_dump_path = _get_db_prod_fixed_dump_path()
    script_path = ctx.obj["store_path"].joinpath("odoo_upgrade.py")
    urlretrieve(ODOO_UPGRADE_SCRIPT, script_path)
    os.chdir(ctx.obj["store_path"])
    cmd = (
        f"TMPDIR=$(mktemp -d) /usr/bin/env python3 {script_path} production "
        f"-c {ctx.obj['contract_number']} "
        f"--dump {prod_dump_path} "
        f"-t {ctx.obj['target_version']} "
        f"--no-restore "
    )
    env_file_path = ctx.obj["odoo_upgrade_env_path"]
    if env_file_path.exists():
        cmd += f"--env-file {env_file_path}"
    ret = subprocess.run(cmd, shell=True, capture_output=True)
    if ret.returncode:
        print("💥 FAILED 💥")
        log_path = ctx.obj["store_path"].joinpath("upgrade.log")
        raise SystemExit(f"=> Check logs located at {log_path}")
    # Sometimes Odoo upgrade script has a returncode == 0 while an error occurred.
    if not upgraded_zip_path.exists() and ret.stderr:
        print("💥 FAILED 💥")
        print("== Logs from Odoo upgrade ==")
        raise SystemExit(ret.stderr.decode())
    print("✅", end="")
    return True


@click.pass_context
def restore_odoo_migrated(ctx):
    # Check if Odoo S.A. database is already restored
    db_name = ctx.obj["db_odoo_migrated"]
    if _db_exists(db_name) and not ctx.params["restart"]:
        print("ℹ️  (skipped: Odoo S.A. migrated database already restored)", end="")
        return False
    # Unzip upgraded.zip archive
    upgraded_zip_path = ctx.obj["store_path"].joinpath("upgraded.zip")
    upgraded_dir_path = ctx.obj["store_path"].joinpath("upgraded")
    assert upgraded_zip_path.exists()
    if not upgraded_dir_path.exists():
        with zipfile.ZipFile(upgraded_zip_path) as upgraded:
            upgraded.extractall(path=upgraded_dir_path)
    # Restore Odoo S.A. migrated database
    container_dump_sql_path = ctx.obj["container_store_path"].joinpath(
        "upgraded", "dump.sql"
    )
    _dropdb(db_name)
    _createdb(db_name)
    mount_opts = f"-v {ctx.obj['store_path']}:/{ctx.obj['container_store_path']}"
    try:
        _run_docker_compose_cmd(
            f"run {mount_opts} -T --rm odoo psql -d {db_name} "
            f"-f {container_dump_sql_path}",
            # Errors regarding owner or extensions for instance could exists
            # in raw SQL file, they have to be ignored.
            raise_on_error=False,
        )
    except subprocess.CalledProcessError:
        print("💥")
        raise
    assert upgraded_dir_path.exists()
    shutil.rmtree(upgraded_dir_path)
    print("✅", end="")
    return True


@click.pass_context
def dump_odoo_migrated(ctx):
    # Dump Odoo S.A. migrated database in a logical/custom Pg format
    # (lighter than raw dump.sql to share it on Celebrimbor afterwards)
    odoo_migrated_path = _get_db_odoo_migrated_dump_path()
    if odoo_migrated_path.exists() and not ctx.params["restart"]:
        print("ℹ️  (skipped: Odoo S.A. migrated dump already exists)", end="")
        return False
    db_name = ctx.obj["db_odoo_migrated"]
    container_odoo_migrated_path = _get_db_odoo_migrated_dump_path(in_container=True)
    mount_opts = f"-v {ctx.obj['store_path']}:/{ctx.obj['container_store_path']}"
    try:
        _run_docker_compose_cmd(
            f"run {mount_opts} --rm odoo pg_dump -b -Fc -d {db_name} "
            f"-f {container_odoo_migrated_path}"
        )
    except subprocess.CalledProcessError:
        print("💥")
        raise
    print("✅", end="")
    return True


@click.pass_context
def migrate_c2c_core(ctx):
    db_core = ctx.obj["db_c2c_core"]
    if (
        _db_exists(db_core)
        and not ctx.params["restart_c2c"]
        and not ctx.params["restart"]
    ):
        print("ℹ️  (skipped: C2C core database already migrated)", end="")
        return False
    # Force next C2C migration steps if '--force-odoo' is set
    if ctx.params["restart"]:
        ctx.params["restart_c2c"] = True
    # Create working database from Odoo S.A. migrated one (template)
    db_odoo_migrated = ctx.obj["db_odoo_migrated"]
    db_name = ctx.obj["db_name"]
    log_file = ctx.obj["store_path"].joinpath(f"{db_name}_c2c_core.log")
    if not _db_exists(db_name) or ctx.params["restart_c2c"]:
        _dropdb(db_name)
        _createdb(db_name, db_template=db_odoo_migrated)
    try:
        make_db_snapshot = 0 if ctx.params["no_db_snapshot"] else 1
        _run_docker_compose_cmd(
            f"run --rm -e DB_NAME={db_name} -e MAKE_DB_SNAPSHOT={make_db_snapshot} "
            f"migrate-db migrate-db-core > {log_file}"
        )
    except subprocess.CalledProcessError:
        print("💥 C2C core migration failed.")
        raise SystemExit(f"=> Check logs located at {log_file}")  # noqa: B904
    print("✅", end="")
    return True


@click.pass_context
def migrate_c2c_external(ctx):
    # Force next C2C migration steps if '--force-c2c-external' is set
    if ctx.params["restart_c2c_external"]:
        ctx.params["restart_c2c"] = True
    db_external = ctx.obj["db_c2c_external"]
    if _db_exists(db_external) and not ctx.params["restart_c2c"]:
        print("ℹ️  (skipped: C2C external database already migrated)", end="")
        return False
    db_name = ctx.obj["db_name"]
    log_file = ctx.obj["store_path"].joinpath(f"{db_name}_c2c_external.log")
    if not _db_exists(db_name) or ctx.params["restart_c2c_external"]:
        db_previous = ctx.obj["db_c2c_core"]
        _dropdb(db_name)
        _createdb(db_name, db_template=db_previous)
    try:
        make_db_snapshot = 0 if ctx.params["no_db_snapshot"] else 1
        _run_docker_compose_cmd(
            f"run --rm -e DB_NAME={db_name} -e MAKE_DB_SNAPSHOT={make_db_snapshot} "
            f"migrate-db migrate-db-external > {log_file}"
        )
    except subprocess.CalledProcessError:
        print("💥 C2C external migration failed.")
        raise SystemExit(f"=> Check logs located at {log_file}")  # noqa: B904
    print("✅", end="")
    return True


@click.pass_context
def migrate_c2c_local(ctx):
    # Force next C2C migration steps if '--force-c2c-local' is set
    if ctx.params["restart_c2c_local"]:
        ctx.params["restart_c2c"] = True
    db_local = ctx.obj["db_c2c_local"]
    if _db_exists(db_local) and not ctx.params["restart_c2c"]:
        print("ℹ️  (skipped: C2C local database already migrated)", end="")
        return False
    db_name = ctx.obj["db_name"]
    log_file = ctx.obj["store_path"].joinpath(f"{db_name}_c2c_local.log")
    if not _db_exists(db_name) or ctx.params["restart_c2c_local"]:
        db_previous = ctx.obj["db_c2c_external"]
        _dropdb(db_name)
        _createdb(db_name, db_template=db_previous)
    try:
        make_db_snapshot = 0 if ctx.params["no_db_snapshot"] else 1
        _run_docker_compose_cmd(
            f"run --rm -e DB_NAME={db_name} -e MAKE_DB_SNAPSHOT={make_db_snapshot} "
            f"migrate-db migrate-db-local > {log_file}"
        )
    except subprocess.CalledProcessError:
        print("💥 C2C local migration failed.")
        raise SystemExit(f"=> Check logs located at {log_file}")  # noqa: B904
    print("✅", end="")
    return True


@click.pass_context
def migrate_c2c_cleanup(ctx):
    # Force next C2C migration steps if '--force-c2c-cleanup' is set
    if ctx.params["restart_c2c_cleanup"]:
        ctx.params["restart_c2c"] = True
    db_cleanup = ctx.obj["db_c2c_cleanup"]
    if _db_exists(db_cleanup) and not ctx.params["restart_c2c"]:
        print("ℹ️  (skipped: C2C cleanup database already migrated)", end="")
        return False
    db_name = ctx.obj["db_name"]
    log_file = ctx.obj["store_path"].joinpath(f"{db_name}_c2c_cleanup.log")
    if not _db_exists(db_name) or ctx.params["restart_c2c_cleanup"]:
        db_previous = ctx.obj["db_c2c_local"]
        _dropdb(db_name)
        _createdb(db_name, db_template=db_previous)
    try:
        make_db_snapshot = 0 if ctx.params["no_db_snapshot"] else 1
        _run_docker_compose_cmd(
            f"run --rm -e DB_NAME={db_name} -e MAKE_DB_SNAPSHOT={make_db_snapshot} "
            f"migrate-db migrate-db-cleanup > {log_file}"
        )
    except subprocess.CalledProcessError:
        print("💥 C2C cleanup migration failed.")
        raise SystemExit(f"=> Check logs located at {log_file}")  # noqa: B904
    print("✅", end="")
    return True


@click.pass_context
def dump_c2c_migrated(ctx):
    c2c_migrated_path = _get_db_c2c_migrated_dump_path()
    if c2c_migrated_path.exists() and not ctx.params["restart_c2c"]:
        print("ℹ️  (skipped: C2C migrated dump already exists)", end="")
        return False
    db_cleanup = ctx.obj["db_c2c_cleanup"]
    assert _db_exists(db_cleanup)
    container_c2c_migrated_path = _get_db_c2c_migrated_dump_path(in_container=True)
    mount_opts = f"-v {ctx.obj['store_path']}:/{ctx.obj['container_store_path']}"
    try:
        _run_docker_compose_cmd(
            f"run {mount_opts} --rm odoo pg_dump -b -Fc -d {db_cleanup} "
            f"-f {container_c2c_migrated_path}"
        )
    except subprocess.CalledProcessError:
        print("💥 Dump of C2C cleanup snapshot failed.")
        raise
    print("✅", end="")
    return True


@click.pass_context
def migration_done(ctx):
    print("✅")
    odoo_migrated_path = _get_db_odoo_migrated_dump_path()
    c2c_migrated_path = _get_db_c2c_migrated_dump_path()
    print("\nYou can now upload on the relevant Celebrimbor environment:")
    print(f"\t- {odoo_migrated_path}")
    print("\t  (useful for your teammates to run C2C migration steps on top of it)")
    print(f"\t- {c2c_migrated_path} (ready to deploy)")


@click.pass_context
def _run_docker_compose_cmd(ctx, cmd, raise_on_error=True, capture_output=True):
    """Run a 'docker compose' command in project folder."""
    base_cmd = f"docker compose --project-directory {ctx.obj['project_path']}"
    full_cmd = f"{base_cmd} {cmd}"
    ret = subprocess.run(full_cmd, shell=True, capture_output=capture_output)
    if raise_on_error:
        ret.check_returncode()
    return ret


@click.pass_context
def _ensure_db_container_is_up(ctx):
    return _run_docker_compose_cmd("up -d db")


@click.pass_context
def _dropdb(ctx, db_name):
    cmd = f"run --rm odoo dropdb --if-exists {db_name}"
    try:
        return _run_docker_compose_cmd(cmd)
    except subprocess.CalledProcessError:
        print(f"💥  Unable to drop DB {db_name}")
        raise SystemExit(f"=> Is there an open connection on {db_name}?") from None


@click.pass_context
def _createdb(ctx, db_name, db_template=None):
    cmd = f"run --rm odoo createdb {db_name}"
    if db_template:
        cmd += f" -T {db_template}"
    try:
        return _run_docker_compose_cmd(cmd)
    except subprocess.CalledProcessError:
        msg = f"💥  Unable to create DB {db_name}"
        if db_template:
            msg += f" from {db_template}"
        print(msg)
        if db_template:
            raise SystemExit(
                f"=> Is there an open connection on {db_template}?"
            ) from None
        raise SystemExit() from None


@click.pass_context
def _get_db_prod_fixed_dump_path(ctx, in_container=False):
    base_path = ctx.obj["store_path"]
    if in_container:
        base_path = ctx.obj["container_store_path"]
    return base_path.joinpath(f"{ctx.obj['db_prod_fixed']}.dump")


@click.pass_context
def _get_db_odoo_migrated_dump_path(ctx, in_container=False):
    base_path = ctx.obj["store_path"]
    if in_container:
        base_path = ctx.obj["container_store_path"]
    return base_path.joinpath(f"{ctx.obj['db_odoo_migrated']}.pg")


@click.pass_context
def _get_db_c2c_migrated_dump_path(ctx, in_container=False):
    base_path = ctx.obj["store_path"]
    if in_container:
        base_path = ctx.obj["container_store_path"]
    return base_path.joinpath(f"{ctx.obj['db_c2c_migrated']}.pg")


@click.pass_context
def _get_db_container_port(ctx):
    """Get and return DB container port."""
    ret = _run_docker_compose_cmd("port db 5432")
    return str(int(ret.stdout.strip().decode().split(":")[-1]))


@click.pass_context
def _execute_db_request(ctx, db_name, sql):
    """Return the execution of given SQL request."""
    result = False
    db_port = _get_db_container_port()
    dsn = f"host=localhost dbname={db_name} user=odoo password=odoo port={db_port}"
    with psycopg2.connect(dsn) as db_connection:
        with db_connection.cursor() as db_cursor:
            db_cursor.execute(sql)
            result = db_cursor.fetchall()
    return result


@click.pass_context
def _db_exists(ctx, db_name):
    res = _execute_db_request(
        "postgres", f"SELECT datname FROM pg_database WHERE datname='{db_name}';"
    )
    return bool(res)


if __name__ == "__main__":
    cli()
