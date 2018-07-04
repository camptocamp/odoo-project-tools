# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from __future__ import print_function

import logging
import re

from itertools import chain

from invoke import task, exceptions
try:
    import git_aggregator.config
    import git_aggregator.main
    import git_aggregator.repo
except ImportError:
    print('Please install git-aggregator')

from .common import (
    cookiecutter_context,
    cd,
    build_path,
    root_path,
    ask_or_abort,
)

BRANCH_EXCLUDE = """
branches:
  except:
    - /^merge-branch-.*$/
"""

@task
def init(ctx):
    """ Add git submodules read in the .gitmodules files

    Allow to edit the .gitmodules file, add all the repositories and
    run the command once to add all the submodules.

    It means less 'git submodule add -b ... {url} {path}' commands to run

    """
    gitmodules = build_path('.gitmodules')
    res = ctx.run(r"git config -f %s --get-regexp '^submodule\..*\.path$'" %
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

    print("Submodules added")
    print()
    print("You can now update odoo/Dockerfile with this addons-path:")
    print()
    list(ctx)


@task(help={
    'dockerfile': 'With --no-dockerfile, the raw paths are listed instead '
                  'of the Dockerfile format'
})
def list(ctx, dockerfile=True):
    """ list git submodules paths

    It can be used to directly copy-paste the addons paths in the Dockerfile.
    The order depends of the order in the .gitmodules file.

    """
    gitmodules = build_path('.gitmodules')
    res = ctx.run(
        "git config --file %s "
        "--get-regexp path | awk '{ print $2 }' " % gitmodules,
        hide=True,
    )
    content = res.stdout
    if dockerfile:
        blacklist = {'odoo/src'}
        lines = (line for line in content.splitlines()
                 if line not in blacklist)
        lines = chain(lines, ['odoo/src/addons', 'odoo/local-src'])
        lines = ("/opt/%s" % line for line in lines)
        template = (
            "ENV ADDONS_PATH=\"%s\" \\\n"
        )
        print(template % (', \\\n'.join(lines)))
    else:
        print(content)


@task
def merges(ctx, submodule_path, push=True):
    """ Regenerate a pending branch for a submodule

    It reads pending-merges.yaml, runs gitaggregator on the submodule and
    pushes the new branch on
    camptocamp/merge-branch-<project_id>-<branch>

    By default, the branch is pushed on the camptocamp remote, but you
    can disable the push with ``--no-push``.

    Example:
    1. Run: git checkout -b my-new-feature-branch
    2. Add pending-merge in odoo/pending-merges.yaml
    3. Run: invoke submodule.merges odoo/external-src/sale-workflow
    4. Run: git add odoo/pending-merges.yaml odoo/external-src/sale-workflow
    5. Run: git commit -m"add PR #XX in sale-workflow"
    6. Create pull request for inclusion in master branch

    Beware, if you changed the remote of the submodule, you still need
    to edit it manually in the ``.gitmodules`` file.

    """
    git_aggregator.main.setup_logger()
    repositories = git_aggregator.config.load_config(
        build_path('odoo/pending-merges.yaml')
    )
    relative_path = submodule_path.lstrip('odoo/')
    for repo_dict in repositories:
        repo = git_aggregator.repo.Repo(**repo_dict)
        if git_aggregator.main.match_dir(repo.cwd, relative_path):
            break
    branch = ctx.run('git symbolic-ref --short HEAD', hide=True).stdout.strip()
    project_id = cookiecutter_context()['project_id']
    commit = ctx.run('git rev-parse HEAD', hide=True).stdout.strip()[:8]
    target = 'merge-branch-{}-{}-{}'.format(project_id, branch, commit)

    if branch == 'master' or re.match(r'\d{1,2}.\d', branch):
        ask_or_abort('You are on branch {}.'
                     ' Please confirm override of target branch {}'.format(
                         branch, target
                     ))

    print('Building and pushing to camptocamp/{}'.format(target))
    print()
    repo.cwd = build_path(submodule_path)
    repo.target['branch'] = target
    repo.aggregate()
    edit_travis_yml(repo)
    commit_travis_yml(repo)
    if push:
        repo.push()


def edit_travis_yml(ctx, repo):
    """
    add config options in .travis.yml file in order to
    prevent travis to run on some branches
    """
    travis_file = "{}/.travis.yml".format(repo.cwd)
    print("Writing exclude branch option in {}".format(travis_file)
    with open(TRAVIS_FILE, 'a') as travis:
        travis.write(BRANCH_EXCLUDE)


def commit_travis_yml(ctx, repo):
    commit = ctx.run(
        'git commit {} -m "Travis: exclude new branch from build"'.format(
            travis_file, hide=True).stdout.strip()[:8]
    print("Committed in {}".format(commit)


@task
def show_closed_prs(ctx, submodule_path=None):
    """ Show all closed pull requests in pending merges """
    git_aggregator.main.setup_logger()
    logging.getLogger('requests').setLevel(logging.ERROR)
    repositories = git_aggregator.config.load_config(
        build_path('odoo/pending-merges.yaml')
    )
    if submodule_path:
        submodule_path = submodule_path.lstrip('odoo/')
    for repo_dict in repositories:
        repo = git_aggregator.repo.Repo(**repo_dict)
        if not git_aggregator.main.match_dir(repo.cwd, submodule_path):
            continue
        try:
            repo.show_closed_prs()
        except AttributeError:
            print('You need to upgrade git-aggregator.'
                  ' This function is available since 1.2.0.')
