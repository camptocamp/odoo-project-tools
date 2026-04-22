# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

import click
from rich.console import Console

from .. import utils
from ..utils import lpass as lpass_utils
from ..utils import password as password_utils
from ..utils.path import build_path

console = Console()

ODOO_PROJECT_URL = "https://{subdomain}.odoo.camptocamp.{country}"


@click.group()
@click.option("--debug", is_flag=True)
@utils.click.version_option
@utils.click.with_update_check
def cli(**kwargs):
    """Password management tools."""


@cli.command()
@click.option(
    "--store-in-lastpass",
    is_flag=True,
    default=False,
    help="Store the generated password in LastPass.",
)
@utils.click.handle_exceptions()
def generate_admin_password(store_in_lastpass):
    """Generate a random admin password and initialize it into songs."""
    password = password_utils.generate()
    encrypted = password_utils.encrypt(password)

    # Replace placeholder in pre.py
    placeholder = "__GENERATED_ADMIN_PASSWORD__"
    pre_file = build_path("odoo/songs/install/pre.py")
    content = pre_file.read_text()
    if placeholder in content:
        pre_file.write_text(content.replace(placeholder, encrypted))
    else:
        utils.ui.exit_msg(f"Placeholder '{placeholder}' not found in {pre_file}")

    console.print(f"[bold]Admin password:[/bold] {password}")
    console.print(f"[bold]Encrypted admin password:[/bold] {encrypted}")

    if store_in_lastpass:
        _store_in_lastpass(password)


def _build_project_url(shortname, country, prefix=None) -> str:
    subdomain = shortname
    if prefix:
        subdomain = f"{prefix}.{shortname}"
    return ODOO_PROJECT_URL.format(subdomain=subdomain, country=country)


def _store_in_lastpass(password, username="admin"):
    """Store the password in LastPass for prod and integration environments."""
    project_name = utils.proj.get_project_manifest_key("project_name")
    shortname = utils.proj.get_project_manifest_key("customer_shortname")
    country = utils.proj.get_project_manifest_key("country")

    locations = [
        ("prod", _build_project_url(shortname, country)),
        ("integration", _build_project_url(shortname, country, prefix="integration")),
    ]
    comment = f"Created automatically on {date.today():%d.%m.%Y}"

    for env, location in locations:
        entry = lpass_utils.make_lastpass_entry(
            env,
            project=project_name,
            shortname=shortname,
            username=username,
            location=location,
            comment=comment,
        )
        try:
            with console.status("Storing password in LastPass..."):
                lpass_utils.store_password_in_lastpass(entry, password)
        except Exception:
            console.print(f"❌ Unable to store Password in LastPass: {entry.location}")
            raise
        else:
            console.print(f"✅ Password stored in LastPass: {entry.location}")
            console.print(lpass_utils.format_lastpass_entry(entry, password))
