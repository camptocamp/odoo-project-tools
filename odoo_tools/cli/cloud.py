# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import subprocess
from pathlib import Path

import click

from .. import utils


def get_customer_name_from_project_name(project_name: str) -> str:
    """Get customer name from project name."""
    return "-".join(project_name.split("_")[:-1])


def build_celebrimbor_command(command, platform=None, customer=None, env="int", *args):
    """Build celebrimbor_cli command."""
    if platform is None:
        platform = utils.proj.get_project_manifest_key("country")
    if customer is None:
        project = utils.proj.get_project_manifest_key("project_name")
        customer = get_customer_name_from_project_name(project)
    return [
        "celebrimbor_cli",
        "--platform",
        platform,
        command,
        "--customer",
        customer,
        "--env",
        env,
        *args,
    ]


def run_celebrimbor(
    command, platform=None, customer=None, env="int", *extra_args, **subprocess_kwargs
):
    """Run celebrimbor_cli with default values from project manifest."""
    if not utils.os_exec.has_exec("celebrimbor_cli"):
        utils.ui.exit_msg(
            "`celebrimbor_cli` is not available. Please go to "
            "https://github.com/camptocamp/celebrimbor-cli and follow the installation "
            "instructions.\n"
            "If it's already installed, please check that it's in your PATH."
        )
        return
    return subprocess.run(
        build_celebrimbor_command(command, platform, customer, env, *extra_args),
        env=utils.os_exec.get_venv(),
        check=True,
        **subprocess_kwargs,
    )


def get_celebrimbor_dump_list(platform=None, customer=None, env="int"):
    """Get list of dumps from the cloud platform."""
    res = run_celebrimbor(
        "list", platform, customer, env, "--raw", capture_output=True
    ).stdout
    return json.loads(res)


@click.group()
@click.option("--debug", is_flag=True)
def cli(**kwargs):
    """Cloud platform commands."""
    pass


@cli.group()
def dump():
    """Cloud platform dump management commands."""
    pass


def common_celebrimbor_options(func):
    """Add common options to the command."""
    click.option(
        "--platform",
        help="Platform to run the command on. Defaults to the project country.",
        default=None,
    )(func)
    click.option(
        "--customer", help="Customer name. Default to the project-name.", default=None
    )(func)
    click.option(
        "--env",
        default="int",
        help="Environment (prod, int, labs.<lab-name>). Defaults to int.",
    )(func)
    return func


@dump.command()
@common_celebrimbor_options
@click.option("--name", help="Specific dump name to download", default=None)
@click.option(
    "--restore-to-db",
    help="If provided, the dump will be restored to this local database after download",
)
@utils.click.handle_exceptions()
def download(platform=None, customer=None, env="prod", name=None, restore_to_db=None):
    """Download a dump from the cloud platform."""
    # We only need it for the restore, so that we know exactly the downloaded file
    if name is None and restore_to_db is not None:
        dump_list = get_celebrimbor_dump_list(platform, customer, env)
        if not dump_list:
            raise click.ClickException("No dump found")
        name = dump_list[-1]["name"]
    # Download using celebrimbor
    extra_args = []
    if name is not None:
        extra_args.extend(["--name", name])
    run_celebrimbor("download", platform, customer, env, *extra_args)
    # Restore if requested
    if restore_to_db:
        dump_path = Path(name.removesuffix(".gpg"))
        utils.db.create_db_from_db_dump(restore_to_db, dump_path)


@dump.command()
@common_celebrimbor_options
@utils.click.handle_exceptions()
def create(platform, customer, env):
    """Generate a new dump on the cloud platform."""
    run_celebrimbor("dump", platform, customer, env)


@dump.command()
@common_celebrimbor_options
@click.argument(
    "dump_path", type=click.Path(exists=True, readable=True), required=False
)
@click.option(
    "--from-db", help="If provided, the dump will be created from this local database"
)
@utils.click.handle_exceptions()
def upload(dump_path, platform, customer, env, from_db):
    """Upload a dump file to the cloud platform."""
    # Check that either dump_path or from_db is provided
    if bool(dump_path) == bool(from_db):
        raise click.UsageError(
            "You must provide either DUMP_PATH or --from-db, but not both."
        )
    if from_db:
        dump_path = utils.db.dump_db(from_db)
    run_celebrimbor("dump", platform, customer, env, "-i", dump_path)


@dump.command()
@common_celebrimbor_options
@click.argument("dump_name", required=False)
@click.option("--from-prod", is_flag=True)
@utils.click.handle_exceptions()
def restore(dump_name, platform, customer, env, from_prod):
    """Restore an uploaded dump on the cloud platform."""
    if bool(dump_name) == bool(from_prod):
        raise click.UsageError(
            "You must provide either DUMP_NAME or --from-prod, but not both."
        )
    if from_prod:
        run_celebrimbor("restore", platform, customer, env, "--from-prod")
    else:
        run_celebrimbor("restore", platform, customer, env, "--name", dump_name)


@dump.command()
@common_celebrimbor_options
@utils.click.handle_exceptions()
def list(platform, customer, env):
    """List available dumps on the cloud platform."""
    run_celebrimbor("list", platform, customer, env)


if __name__ == "__main__":
    cli()
