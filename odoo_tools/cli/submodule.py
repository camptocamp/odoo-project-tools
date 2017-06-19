# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from __future__ import print_function


from invoke import task, exceptions
from .common import (
    cookiecutter_context,
    cd,
    build_path,
    root_path,
)


@task
def init(ctx):
    """ Add git submodules read in the .gitmodules files

    Allow to edit the .gitmodules file, add all the repositories and
    run the command once to add all the submodules.

    It means less 'git submodule add -b ... {url} {path}' commands to run

    """
    gitmodules = build_path('.gitmodules')
    res = ctx.run("git config -f %s --get-regexp '^submodule\..*\.path$'" %
                  gitmodules, hide=True)
    odoo_version = cookiecutter_context()['odoo_version']
    with cd(root_path()):
        for line in res.stdout.splitlines():
            path_key, path = line.split()
            url_key = path_key.replace('.path', '.url')
            url = ctx.run('git config -f %s --get "%s"' %
                          (gitmodules, url_key), hide=True).stdout
            try:
                ctx.run('git submodule add -b %s %s %s' %
                        (odoo_version, url.strip(), path.strip()))
            except exceptions.Failure:
                pass
