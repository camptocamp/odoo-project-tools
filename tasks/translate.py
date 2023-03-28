# Copyright 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import glob
import os

from invoke import task

from .common import build_path


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
    assert os.path.exists(build_path(addon_path)), "%s not found" % addon_path
    container_path = os.path.join("/", addon_path, "i18n")
    i18n_dir = os.path.join(build_path(addon_path), "i18n")
    if not os.path.exists(i18n_dir):
        os.mkdir(i18n_dir)
    container_po_path = os.path.join(container_path, "%s.po" % addon)
    user_id = ctx.run("id --user", hide="both").stdout.strip()
    cmd_init = (
        "docker-compose run --rm  -e LOCAL_USER_ID=%(user)s "
        "-e DEMO=False -e MIGRATE=False odoo odoo "
        "--log-level=warn --workers=0 "
        "--database %(dbname)s "
        "--stop-after-init --without-demo=all "
        "--init=%(addon)s"
    ) % {"user": user_id, "dbname": dbname, "addon": addon}
    cmd_gen = (
        "docker-compose run --rm  -e LOCAL_USER_ID=%(user)s "
        "-e DEMO=False -e MIGRATE=False odoo odoo "
        "--log-level=warn --workers=0 "
        "--database %(dbname)s --i18n-export=%(path)s "
        "--modules=%(addon)s --stop-after-init --without-demo=all "
    ) % {
        "user": user_id,
        "path": container_po_path,
        "dbname": dbname,
        "addon": addon,
    }
    ctx.run(cmd_init)
    ctx.run(cmd_gen)

    ctx.run(
        "docker-compose run --rm -e PGPASSWORD=odoo odoo "
        "dropdb %s -U odoo -h db" % dbname
    )

    # mv .po to .pot
    source = os.path.join(i18n_dir, "%s.po" % addon)
    pot_file = source + "t"
    # dirty hack to remove duplicated entries for paths
    ctx.run("mv {} {}".format(source, pot_file))
    ctx.run(r'sed -i "/local-src\|external-src/d" {pot}'.format(pot=pot_file))

    if update_po:
        for po_file in glob.glob("%s/*.po" % i18n_dir):
            ctx.run("msgmerge {po} {pot} -o {po}".format(po=po_file, pot=pot_file))
            # dirty hack to remove duplicated entries for paths
            ctx.run(r'sed -i "/local-src\|external-src/d" {po}'.format(po=po_file))
    print("%s.pot generated" % addon)
