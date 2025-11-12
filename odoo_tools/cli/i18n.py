# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import tempfile
from pathlib import Path

import click
from rich.console import Console

from .. import utils

console = Console()


@click.group()
@click.option("--debug", is_flag=True)
def cli(**kwargs):
    """Internationalization (i18n) commands."""
    pass


@cli.command()
@click.argument(
    "module_paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=True, file_okay=False, readable=True),
)
@click.option(
    "--languages",
    type=str,
    required=False,
    default=None,
    help="Comma separated list of languages to export. Defaults to all project languages.",
)
@click.option(
    "--clean-db/--no-clean-db",
    default=True,
    help="Clean the translation database before exporting",
)
@click.option(
    "--init-db/--no-init-db",
    default=True,
    help="Initialize the translation database before exporting",
)
@click.option("--export-pot/--no-export-pot", default=False, help="Export the pot file")
@utils.click.handle_exceptions()
def export(module_paths, languages, clean_db, init_db, export_pot):
    """Export the translation files for a given module."""
    # Identify the module names to export, from the module paths
    module_names = [
        module_path.name
        for module_path in (Path(path) for path in module_paths)
        if utils.path.is_odoo_module(module_path)
    ]
    if not module_names:
        raise click.ClickException(
            "No modules found to export. Please specify at least one module path."
        )
    # Identify languages to export
    # If it's specified, parse the csv. Otherwise use the project languages.
    if languages:
        languages = languages.split(",")
    else:
        languages = []
        if main_lang := utils.proj.get_project_manifest_key("odoo_main_lang"):
            languages.append(main_lang)
        if aux_langs := utils.proj.get_project_manifest_key("odoo_aux_langs"):
            languages.extend(aux_langs.split(","))
    # Prepare the languages for export. We ignore en_US because it requires no
    # translations, and we add None for the pot files, if needed.
    export_languages = tuple[str](lang for lang in languages if lang != "en_US")
    if export_pot:
        export_languages = (None, *export_languages)
    if not export_languages:
        raise click.ClickException("Please specify at least one language.")
    # Cleanup the translation database if it already exists, to re-load languages
    if clean_db:
        with console.status("Cleaning up translation database..."):
            utils.os_exec.run(utils.docker_compose.drop_db("tmp_generate_pot"))
    else:
        console.print(
            "⚠️ Not cleaning up translation database may cause wrong terms "
            "to be exported due to oudated module data.",
            style="yellow",
        )
    # Initialize the translation database with the terms
    if init_db:
        with console.status(
            f"Initializing Odoo database for i18n export: {', '.join(module_names)}"
        ):
            utils.os_exec.run(
                utils.docker_compose.run(
                    "odoo",
                    [
                        "odoo",
                        "--log-level=warn",
                        "--workers=0",
                        "--database=tmp_generate_pot",
                        f"--load-language={','.join(languages)}",
                        "--stop-after-init",
                        f"--init={','.join(module_names)}",
                    ],
                    environment={
                        "DEMO": "True",
                        "MIGRATE": "False",
                    },
                    quiet=False,
                ),
                check=True,
            )
    else:
        console.print(
            "🚨 Not initializing Odoo database. We're not even checking the modules "
            "are installed, or that their terms ar up to date. Use at your own risk, "
            "and only if you are sure the database is up to date."
        )
    # Export module by module and language by language
    # TODO: Find a faster way to do this? Parallelize?
    for idx, module_path in enumerate(module_paths):
        # Local path to the module
        local_path = utils.path.build_path(module_path)
        module_name = local_path.name
        progress = f"{idx + 1}/{len(module_paths)}"
        # Create a temporary directory to mount onto the container as volume
        with console.status(f"({progress}) {module_name}...") as status:
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Export the translation files
                local_volume_path = Path(tmp_dir)
                container_volume_path = Path("/tmp/otools_i18n")
                for language in export_languages:
                    i18n_filename = (
                        f"{module_name}.pot" if language is None else f"{language}.po"
                    )
                    i18n_rel_path = Path(module_name) / "i18n" / i18n_filename
                    status.update(f"({progress}) {i18n_rel_path}...")
                    odoo_cmd = [
                        "odoo",
                        "--log-level=warn",
                        "--workers=0",
                        "--database=tmp_generate_pot",
                        "--stop-after-init",
                        f"--i18n-export={container_volume_path / i18n_filename}",
                        f"--modules={module_name}",
                    ]
                    if language is not None:
                        odoo_cmd.append(f"--language={language}")
                    utils.os_exec.run(
                        utils.docker_compose.run(
                            "odoo",
                            odoo_cmd,
                            environment={
                                "DEMO": "True",
                                "MIGRATE": "False",
                            },
                            volumes=[(local_volume_path, container_volume_path)],
                        ),
                        check=True,
                    )
                    # Move the file to the local module directory
                    source_file = local_volume_path / i18n_filename
                    target_file = local_path / "i18n" / i18n_filename
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    if not source_file.exists():
                        raise FileNotFoundError(source_file.as_posix())
                    elif not source_file.is_file():
                        raise IsADirectoryError(source_file.as_posix())
                    source_file.replace(target_file)
                    # Print a message
                    console.print(
                        f"✅ {target_file.relative_to(Path.cwd()).as_posix()}"
                    )


if __name__ == "__main__":
    cli()
