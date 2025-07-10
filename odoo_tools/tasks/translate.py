# Copyright 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import glob
import os

from invoke import task

from ..utils.path import build_path


@task(default=True)
def generate(ctx, addon_path, update_po=True):
    """Generate pot template and merge it in language files

    Example:

        $ invoke translate.generate odoo/local-src/my_module
    """
    # TODO: change depending on new structure
    # use root_path to get root project directory
    dbname = "tmp_generate_pot"
    addon = addon_path.strip("/").split("/")[-1]
    path = build_path(addon_path)
    assert path.exists(), f"{addon_path} not found"
    container_path = os.path.join("/", addon_path, "i18n")
    i18n_dir = path / "i18n"
    if not i18n_dir.exists():
        os.mkdir(i18n_dir)
    container_po_path = os.path.join(container_path, f"{addon}.po")
    user_id = ctx.run("id --user", hide="both").stdout.strip()
    cmd_init = (
        f"docker compose run --rm -e LOCAL_USER_ID={user_id} "
        "-e DEMO=False -e MIGRATE=False odoo odoo "
        "--log-level=warn --workers=0 "
        f"--database {dbname} "
        "--stop-after-init --without-demo=all "
        f"--init={addon}"
    )
    cmd_gen = (
        f"docker compose run --rm -e LOCAL_USER_ID={user_id} "
        "-e DEMO=False -e MIGRATE=False odoo odoo "
        "--log-level=warn --workers=0 "
        f"--database {dbname} --i18n-export={container_po_path} "
        f"--modules={addon} --stop-after-init --without-demo=all"
    )
    ctx.run(cmd_init)
    ctx.run(cmd_gen)

    ctx.run(
        "docker compose run --rm -e PGPASSWORD=odoo odoo "
        f"dropdb {dbname} -U odoo -h db"
    )

    # mv .po to .pot
    source = os.path.join(i18n_dir, f"{addon}.po")
    pot_file = source + "t"
    # dirty hack to remove duplicated entries for paths
    ctx.run(f"mv {source} {pot_file}")
    ctx.run(rf'sed -i "/local-src\|external-src/d" {pot_file}')

    if update_po:
        for po_file in glob.glob(f"{i18n_dir}/*.po"):
            ctx.run(f"msgmerge {po_file} {pot_file} -o {po_file}")
            # dirty hack to remove duplicated entries for paths
            ctx.run(rf'sed -i "/local-src\|external-src/d" {po_file}')
    print(f"{addon}.pot generated")
