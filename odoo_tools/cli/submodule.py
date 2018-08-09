# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from __future__ import print_function

import logging
import os
import re
from itertools import chain

from invoke import task, exceptions
try:
    import git_aggregator.config
    import git_aggregator.main
    import git_aggregator.repo
except ImportError:
    print('Missing git-aggregator from requirements')
    print('Please run `pip install -r tasks/requirements.txt`')

try:
    import git_autoshare
    AUTOSHARE_ENABLED = True
except ImportError:
    print('Missing git-autoshare from requirements')
    print('Please run `pip install -r tasks/requirements.txt`')
    AUTOSHARE_ENABLED = False
import requests

from invoke import exceptions, task

from .common import (
    GIT_REMOTE_NAME,
    PENDING_MERGES_DIR,
    ask_confirmation,
    ask_or_abort,
    build_path,
    build_github_remote_url,
    cd,
    cookiecutter_context,
    exit_msg,
    get_aggregator_repo,
    get_aggregator_repositories,
    build_submodule_path,
    build_submodule_merges_path,
    root_path,
)

try:
    import git_aggregator.config
    import git_aggregator.main
    import git_aggregator.repo
except ImportError:
    print('Please install git-aggregator')

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedSeq
except ImportError:
    print('Please install ruamel.yaml')

try:
    input = raw_input
except NameError:
    pass

BRANCH_EXCLUDE = """
branches:
  except:
    - /^merge-branch-.*$/
"""
yaml = YAML()


def get_target_branch(ctx, target_branch=None):
    """Gets the branch to push on and checks if we're overriding something.

    If target_branch is given only checks for the override.
    Otherwise create the branch name and check for the override.
    """
    current_branch = ctx.run(
        'git symbolic-ref --short HEAD', hide=True).stdout.strip()
    project_id = cookiecutter_context()['project_id']
    if not target_branch:
        commit = ctx.run('git rev-parse HEAD', hide=True).stdout.strip()[:8]
        target_branch = 'merge-branch-{}-{}-{}'.format(
            project_id, current_branch, commit)
    if current_branch == 'master' or re.match(r'\d{1,2}.\d', target_branch):
        ask_or_abort('You are on branch {}.'
                     ' Please confirm override of target branch {}'.format(
                         current_branch, target_branch
                     ))
    return target_branch


@task
def init(ctx):
    """ Add git submodules read in the .gitmodules files

    Allow to edit the .gitmodules file, add all the repositories and
    run the command once to add all the submodules.

    It means less 'git submodule add -b ... {url} {path}' commands to run

    """
    add_command = 'git submodule add'
    if AUTOSHARE_ENABLED:
        add_command = 'git autoshare-submodule-add'
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
                ctx.run('%s -b %s %s %s' %
                        (add_command, odoo_version, url.strip(), path.strip()))
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
        lines = ("/%s" % line for line in lines)
        template = (
            "ENV ADDONS_PATH=\"%s\" \\\n"
        )
        print(template % (', \\\n'.join(lines)))
    else:
        print(content)


@task
def merges(ctx, submodule_path, push=True, target_branch=None):
    """Regenerate a pending branch for a submodule.

    It reads pending-merges.d/sub-name.yml, runs gitaggregator on the submodule
    and pushes the new branch on dynamic target constructed as follows:
    camptocamp/merge-branch-<project_id>-<branch>-<commit>

    By default, the branch is pushed on the camptocamp remote, but you
    can disable the push with ``--no-push``.

    Example:
    1. Run: git checkout -b my-new-feature-branch
    2. Add pending-merge in pending-merges.d/sale-workflow.yml
    3. Run: invoke submodule.merges odoo/external-src/sale-workflow
    4. Run: git add pending-merges.d/sale-workflow.yml odoo/external-src/sale-workflow
    5. Run: git commit -m"add PR #XX in sale-workflow"
    6. Create pull request for inclusion in master branch

    Beware, if you changed the remote of the submodule, you still need
    to edit it manually in the ``.gitmodules`` file.
    """
    # First of all, check if there's a migration file at the old path
    if os.path.exists('odoo/pending-merges.yaml'):
        # notify ppl that this file was moved, then terminate execution
        exit_msg(
            'Found a file in \'odoo/pending-merges.yaml\'.'
            ' Please run `invoke deprecate.move-pending-merges\' task first.')

    # ensure that given submodule is a mature submodule
    if not os.path.exists(os.path.join(submodule_path, '.git')):
        exit_msg('{} does not look like a mature repository. Aborting.'.format(
            submodule_path))

    # Second: check if there's a config for the requested repo around
    # we only need a repo name, actually, not the full path
    repo_merges_file = build_submodule_merges_path(submodule_path)
    if not os.path.exists(repo_merges_file):
        exit_msg('Nothing to push for `{}\'.'.format(submodule_path))
    # Aight, we good to go here.
    git_aggregator.main.setup_logger()

    # as there's only one repo config per file
    # resolve the target for a push
    project_id = cookiecutter_context()['project_id']
    # branch of the master repository, this has nothing to do w/ the submodule
    branch = ctx.run('git symbolic-ref --short HEAD', hide=True).stdout.strip()
    commit_hash = ctx.run('git rev-parse HEAD', hide=True).stdout.strip()[:8]
    target = 'merge-branch-{}-{}-{}'.format(project_id, branch, commit_hash)

    if branch == 'master' or re.match(r'^\d{1,2}\.\d$', branch):
        ask_or_abort(
            'You are on branch {}. Please confirm override of target branch {}'
            .format(branch, target))

    print('Building and pushing to camptocamp/{}'.format(target_branch))
    print()
    repo_config = git_aggregator.config.load_config(repo_merges_file)[0]
    repo_config['target'] = {
        'branch': target,
        'remote': GIT_REMOTE_NAME,
    }
    repo = git_aggregator.repo.Repo(**repo_config)
    repo.cwd = build_path(submodule_path)
    repo.aggregate()

    process_travis_file(ctx, repo)
    if push:
        repo.push()


@task
def push(ctx, submodule_path, target_branch=None):
    """Push a Submodule

    Pushes the current state of your submodule to the target remote and branch
    either given by you or specified in pending-merges.yml
    """
    git_aggregator.main.setup_logger()
    repo = get_aggregator_repo(submodule_path)
    target_branch = get_target_branch(ctx, target_branch)
    print('Pushing to {}/{}'.format(repo.target['remote'], target_branch))
    print()
    repo.cwd = build_path(submodule_path)
    repo.target['branch'] = target_branch
    with cd(submodule_path):
        repo._switch_to_branch(target_branch)
        process_travis_file(ctx, repo)
        repo.push()


def process_travis_file(ctx, repo):
    tf = '.travis.yml'
    with cd(repo.cwd):
        if not os.path.exists(tf):
            print(repo.cwd + tf,
                  'does not exists. Skipping travis exclude commit')
            return

        print("Writing exclude branch option in {}".format(tf))
        with open(tf, 'a') as travis:
            travis.write(BRANCH_EXCLUDE)

        cmd = 'git commit {} -m "Travis: exclude new branch from build"'
        commit = ctx.run(cmd.format(tf), hide=True)
        print("Committed as:\n{}".format(commit.stdout.strip()))


@task
def show_closed_prs(ctx, submodule_path='all'):
    """Show all closed pull requests in pending merges.

    Pass nothing to check all submodules.
    Pass `-s path/to/submodule` to check specific ones.
    """
    git_aggregator.main.setup_logger()
    logging.getLogger('requests').setLevel(logging.ERROR)
    if submodule_path == 'all':
        repositories = get_aggregator_repositories()
    else:
        repositories = [get_aggregator_repo(submodule_path)]
    if not repositories:
        exit_msg('No repo to check.')
    try:
        for repo in repositories:
            print('Checking', repo.cwd)
            repo.show_closed_prs()
    except AttributeError:
        print('You need to upgrade git-aggregator.'
              ' This function is available since 1.2.0.')


@task
def update(ctx, submodule_path=None):
    """Synchronize and update given submodule path

    :param submodule_path: submodule path for a precise sync & update
    """
    sync_cmd = 'git submodule sync'
    update_cmd = 'git submodule update --init'
    if submodule_path is not None:
        sync_cmd += ' -- {}'.format(submodule_path)
        update_cmd += ' -- {}'.format(submodule_path)
    with cd(root_path()):
        ctx.run(sync_cmd)
        ctx.run(update_cmd)


@task
def sync_remote(ctx, submodule_path, force_remote=False):
    """Use to alter remotes between camptocamp and upstream in .gitmodules.

    :param force_remote: explicit remote to add, if omitted, acts this way:
    * sets upstream to `camptocamp` if `merges` section of it's pending-merges
      file is populated
    * tries to guess upstream otherwise - for `odoo/src` path it is usually
      `OCA/OCB` repository, for anything else it would search for a fork in a
      `camptocamp` namespace and then set the upstream to fork's parent
    Mainly used as a post-execution step for add/remove-pending-merge but it's
    possible to call it directly from the command line.
    """
    submodule_pending_merges_path = build_submodule_merges_path(submodule_path)
    has_pending_merges = os.path.exists(submodule_pending_merges_path)

    if has_pending_merges:
        with open(submodule_pending_merges_path) as pending_merges:
            # read everything we can reach
            # for reading purposes only
            data = yaml.load(pending_merges.read())
            submodule_pending_config = data[
                os.path.join(os.path.pardir, submodule_path)
            ]
            merges_in_action = submodule_pending_config['merges']
            registered_remotes = submodule_pending_config['remotes']

            if force_remote:
                new_remote_url = registered_remotes[force_remote]
            elif merges_in_action:
                new_remote_url = registered_remotes[GIT_REMOTE_NAME]
            else:
                new_remote_url = next(
                    remote for remote in registered_remotes.values()
                    if remote != GIT_REMOTE_NAME)
    elif submodule_path == 'odoo/src':
        # special way to treat that particular submodule
        # TODO: ask user if it's preferred to use `odoo/odoo` instead?
        if ask_confirmation('Use odoo:odoo instead of OCA/OCB?'):
            new_remote_url = build_github_remote_url('odoo', 'odoo')
        else:
            new_remote_url = build_github_remote_url('OCA', 'OCB')
    else:
        # resolve what's the parent repository from which C2C consolidation
        # one was forked
        submodule_name = submodule_path.split('/')[-1].strip()
        response = requests.get(
            'https://api.github.com/repos/{}/{}'
            .format(GIT_REMOTE_NAME, submodule_name))
        if response.ok:
            new_remote_url \
                = response.json().get('parent', {}).get('ssh_url')
        else:
            print("Couldn't reach Github API to resolve submodule upstream."
                  " Please provide it manually.")
            default_repo = submodule_name.replace('_', '-')
            new_namespace = input('Namespace [OCA]: ') or 'OCA'
            new_repo = input('Repo name [{}]: '.format(default_repo)) \
                or default_repo
            new_remote_url = build_github_remote_url(
                new_namespace, new_repo)

    submodule_path = submodule_path.lstrip('./')
    ctx.run('git config --file=.gitmodules submodule.{}.url {}'.format(
        submodule_path, new_remote_url))
    relative_name = submodule_path.replace('../', '')
    with cd(build_path(relative_name)):
        ctx.run('git remote set-url origin {}'.format(new_remote_url))

    print('Submodule {} is now being sourced from {}'.format(
        submodule_path, new_remote_url))

    if has_pending_merges:
        # we're being polite here, excode 1 doesn't apply to this answer
        if not ask_confirmation(
                'Rebuild consolidation branch for {}?'.format(relative_name)):
            return

        push = ask_confirmation('Push it to `{}\'?'.format(GIT_REMOTE_NAME))
        merges(ctx, relative_name, push=push)
    else:
        if ask_confirmation(
                'Submodule {} has no pending merges. Update it to {}?'
                .format(relative_name, cookiecutter_context()['odoo_version'])
        ):
            with cd(build_path(relative_name)):
                os.system('git fetch origin {{cookiecutter.odoo_version}}')
                os.system('git checkout origin/{{cookiecutter.odoo_version}}')


def parse_github_url(entity_spec):
    # "entity" is either a PR, commit or a branch
    # TODO: input validation

    # check if it's in a custom pull format // nmspc/repo#pull
    custom_parts = re.match(r'([\w-]+)/([\w-]+)#(\d+)', entity_spec)
    if custom_parts:
        entity_type = 'pull'
        upstream, repo_name, entity_id = custom_parts.groups()
    else:
        # this is meant to be an web link then
        # Example:
        # https://github.com/namespace/repo/pull/1234/files#diff-deadbeef
        # parts 0, 1 and 2  /    p3   / p4 / p5 / p6 | part to trim
        #                    ========= ==== ==== ====
        # as we're not interested in parts 7 and beyond, we're just trimming it
        # this is done to allow passing link w/ trailing garbage to this task
        upstream, repo_name, entity_type, entity_id \
            = entity_spec.split('/')[3:7]

    # force uppercase in OCA upstream name:
    # otherwise `oca` and `OCA` are treated as different namespaces
    if upstream.lower() == 'oca':
        upstream = 'OCA'

    return {
        'upstream': upstream,
        'repo_name': repo_name,
        'entity_type': entity_type,
        'entity_id': entity_id,
    }


def generate_pending_merges_file_template(
        pending_mrg_filepath, upstream, repo_name):
    # create a submodule merges file from template
    # that should be either `odoo/src` or `odoo/external-src/<module>`

    # could be that this is the first PM ever added to this project
    if not os.path.exists(PENDING_MERGES_DIR):
        os.makedirs(PENDING_MERGES_DIR)

    remote_upstream_url = build_github_remote_url(upstream, repo_name)
    remote_c2c_url = build_github_remote_url(GIT_REMOTE_NAME, repo_name)
    submodule_path = os.path.join(
        os.path.pardir, build_submodule_path(repo_name))
    odoo_version = cookiecutter_context().get('odoo_version')

    template_content = '\n'.join([
        '{}:'.format(submodule_path),
        '  remotes:',
        '    {}: {}'.format(upstream, remote_upstream_url),
        '    {}: {}'.format(GIT_REMOTE_NAME, remote_c2c_url),
        '  merges:',
        '    - {} {}'.format(upstream, odoo_version),
        '  target: {} {}'.format(GIT_REMOTE_NAME, 'dummy-target'),
        '',
    ])
    with open(pending_mrg_filepath, 'w') as f:
        # let `yaml` handle document structure
        yaml.dump(yaml.load(template_content), f)


def add_pending_pull_request(conf, upstream, repo_name, pull_id):
    pending_mrg_line = '{} refs/pull/{}/head'.format(upstream, pull_id)
    pending_mrg_filepath = build_submodule_merges_path(repo_name)

    response = requests.get(
        'https://api.github.com/repos/'
        '{upstream}/{repo_name}/pulls/{pull_id}'
        .format(**locals()))

    # TODO: auth
    base_branch = response.json().get('base', {}).get('ref')
    if response.ok:
        if base_branch:
            odoo_version = cookiecutter_context().get('odoo_version')
            if base_branch != odoo_version:
                ask_or_abort('Requested PR targets branch different from'
                             ' current project\'s major version. Proceed?')
    else:
        print('Github API call failed ({}):'
              ' skipping target branch validation.'
              .format(response.status_code))

    if response.ok:
        # probably, wrapping `if` could be an overkill
        pending_mrg_comment = response.json().get('title')
    else:
        pending_mrg_comment = False
        print('Unable to get a pull request title.'
              ' You can provide it manually by editing {}.'.format(
                  pending_mrg_filepath))

    # prepend path w/ `parent directory` expression to make it
    # relative to files in `pending-merges.d`
    submodule_path = os.path.join(
        os.path.pardir, build_submodule_path(repo_name))

    known_remotes = conf['remotes']

    if pending_mrg_line in conf['merges']:
        exit_msg('Requested pending merge is mentioned in {} already'
                 .format(pending_mrg_filepath))

    if upstream not in known_remotes:
        # ruamel struggles to insert a comment here, fut fails drastically.
        known_remotes.insert(
            0, upstream, build_github_remote_url(upstream, repo_name),
            comment=pending_mrg_comment)

    # we're just at the place to append a new pending merge
    # ruamel.yaml's API won't allow ppl to insert items at the end of
    # array, so the closest solution would be to insert it at position 1,
    # straight after `OCA basebranch` merge item.
    conf['merges'].insert(1, pending_mrg_line)


def add_pending_commit(conf, upstream, repo_name, commit_sha):
    if len(commit_sha) < 40:
        ask_or_abort(
            "You are about to add a patch referenced by a short commit SHA.\n"
            "It's recommended to use fully qualified 40-digit hashes though.\n"
            "Continue?")
    pending_mrg_line \
        = 'git am "$(git format-patch -1 {} -o ../patches)"'.format(commit_sha)
    pending_mrg_filepath = build_submodule_merges_path(repo_name)

    if pending_mrg_line in conf.get('shell_command_after', {}):
        exit_msg('Requested pending merge is mentioned in {} already'
                 .format(pending_mrg_filepath))
    if 'shell_command_after' not in conf:
        conf['shell_command_after'] = CommentedSeq()

    # TODO: make comments great again
    # This snippet was written according to ruamel.yaml docs, though not a
    # single attempt to preserve/provide comments was successful
    # https://yaml.readthedocs.io/en/latest/example.html
    # comment = input(
    #     'Comment? '
    #     '(would appear just above new pending merge, optional):\n')
    # conf['shell_command_after'].insert(1, pending_mrg_line, comment)
    conf['shell_command_after'].insert(1, pending_mrg_line)


@task
def add_pending(ctx, entity_url):
    """Add a pending merge using given entity link"""
    # pattern, given an https://github.com/<upstream>/<repo>/pull/<pr-index>
    # # PR headline
    # # PR link as is
    # - refs/pull/<pr-index>/head
    parts = parse_github_url(entity_url)

    upstream = parts.get('upstream')
    repo_name = parts.get('repo_name')
    entity_type = parts.get('entity_type')
    entity_id = parts.get('entity_id')
    pending_mrg_filepath = build_submodule_merges_path(repo_name)

    if not os.path.exists(pending_mrg_filepath):
        generate_pending_merges_file_template(
            pending_mrg_filepath, upstream, repo_name)

    # TODO: adding comments doesn't really work :/
    with open(pending_mrg_filepath) as f:
        data = yaml.load(f.read())
        submodule_relpath \
            = os.path.join(os.path.pardir, build_submodule_path(repo_name))
        conf = data[submodule_relpath]

    if entity_type == 'pull':
        add_pending_pull_request(conf, upstream, repo_name, entity_id)
    elif entity_type in ('commit', 'tree'):
        add_pending_commit(conf, upstream, repo_name, entity_id)

    # write back a file
    with open(pending_mrg_filepath, 'w') as f:
        yaml.dump(data, f)
        sync_remote(ctx, build_submodule_path(repo_name))


def remove_pending_commit(conf, upstream, commit_sha, pending_mrg_filepath):
    line_to_drop \
        = 'git am "$(git format-patch -1 {} -o ../patches)"'.format(commit_sha)
    if line_to_drop not in conf.get('shell_command_after', {}):
        exit_msg('No such reference found in {},'
                 ' having troubles removing that:\n'
                 'Looking for: {}'
                 .format(pending_mrg_filepath, line_to_drop))
    conf['shell_command_after'].remove(line_to_drop)
    if not conf['shell_command_after']:
        del conf['shell_command_after']


def remove_pending_pull(conf, upstream, pull_id, pending_mrg_filepath):
    line_to_drop = '{} refs/pull/{}/head'.format(upstream, pull_id)
    if line_to_drop not in conf['merges']:
        exit_msg('No such reference found in {},'
                 ' having troubles removing that:\n'
                 'Looking for: {}'
                 .format(pending_mrg_filepath, line_to_drop))
    conf['merges'].remove(line_to_drop)


@task
def remove_pending(ctx, entity_url):
    """Remove a pending merge using given entity link"""

    parts = parse_github_url(entity_url)

    upstream = parts.get('upstream')
    repo_name = parts.get('repo_name')
    submodule_path = os.path.join(
        os.path.pardir, build_submodule_path(repo_name))
    entity_type = parts.get('entity_type')
    entity_id = parts.get('entity_id')

    pending_mrg_filepath = build_submodule_merges_path(repo_name)

    if not os.path.exists(pending_mrg_filepath):
        exit_msg('No file found at {}'.format(pending_mrg_filepath))

    with open(pending_mrg_filepath) as f:
        data = yaml.load(f.read())
        submodule_config = data[submodule_path]
        if entity_type == 'pull':
            remove_pending_pull(
                submodule_config, upstream, entity_id, pending_mrg_filepath)
        elif entity_type in ('tree', 'commit'):
            remove_pending_commit(
                submodule_config, upstream, entity_id, pending_mrg_filepath)

    # check if that file is useless since it has an empty `merges` section
    # if it does - drop it instead of writing a new file version
    # only the upstream branch is present in `merges`
    # first item is `- oca {{cookiecutter.odoo_version}}` or similar
    pending_merges_present = len(submodule_config['merges']) > 1
    patches = len(submodule_config.get('shell_command_after', {}))

    if not pending_merges_present and not patches:
        os.remove(pending_mrg_filepath)
        sync_remote(ctx, submodule_path)
    else:
        with open(pending_mrg_filepath, 'w') as f:
            yaml.dump(data, f)
