# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from __future__ import print_function

import logging
import os
import re
from itertools import chain

import requests
from invoke import exceptions, task

from .common import (
    GIT_C2C_REMOTE_NAME,
    PENDING_MERGES_DIR,
    ask_confirmation,
    ask_or_abort,
    build_path,
    cd,
    cookiecutter_context,
    exit_msg,
    root_path,
)

try:
    import git_aggregator.config
    import git_aggregator.main
    import git_aggregator.repo
except ImportError:
    print('Missing git-aggregator from requirements')
    print('Please run `pip install -r tasks/requirements.txt`')

try:
    import git_autoshare  # noqa: F401

    AUTOSHARE_ENABLED = True
except ImportError:
    print('Missing git-autoshare from requirements')
    print('Please run `pip install -r tasks/requirements.txt`')
    AUTOSHARE_ENABLED = False


try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedSeq
    from ruamel.yaml.comments import CommentedMap
except ImportError:
    print('Missing ruamel.yaml from requirements')
    print('Please run `pip install -r tasks/requirements.txt`')


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

git_aggregator.main.setup_logger()


class Repo(object):
    """Handle repository/submodule homogenously."""

    def __init__(self, name_or_path, path_check=True):
        self.path = self.build_submodule_path(name_or_path)
        self.abs_path = build_path(self.path)
        # ensure that given submodule is a mature submodule
        self.abs_merges_path = self.build_submodule_merges_path(self.path)
        self.merges_path = self.build_submodule_merges_path(
            self.path, relative=True
        )
        if path_check:
            self._check_paths()
        self.name = self._safe_module_name(name_or_path)

    def _check_paths(self):
        if not os.path.exists(os.path.join(self.path, '.git')):
            exit_msg(
                'GIT CONFIG NOT FOUND. '
                '{} does not look like a mature repository. '
                'Aborting.'.format(self.path)
            )
        if not os.path.exists(self.abs_merges_path):
            exit_msg('NOT FOUND `{}\'.'.format(self.abs_merges_path))

    @classmethod
    def _safe_module_name(cls, name_or_path):
        return name_or_path.rstrip('/').rsplit('/', 1)[-1]

    @classmethod
    def build_submodule_path(cls, name_or_path):
        """Return a submodule path by a submodule name."""
        submodule_name = cls._safe_module_name(name_or_path)
        is_src = submodule_name in ('odoo', 'ocb', 'src')
        if is_src:
            relative_path = 'odoo/src'
        else:
            relative_path = 'odoo/external-src/{}'.format(submodule_name)
        return relative_path

    @classmethod
    def build_submodule_merges_path(cls, name_or_path, relative=False):
        """Return a pending-merges file for a given submodule.

        :param submodule: either a full path or a bare submodule name,
        as it is known at Github (i.e., `odoo` would stand for `odoo/src`)
        """
        submodule_name = cls._safe_module_name(name_or_path)
        if submodule_name.lower() in ('odoo', 'ocb'):
            submodule_name = 'src'
        base_path = PENDING_MERGES_DIR
        if relative:
            base_path = os.path.basename(PENDING_MERGES_DIR)
        return '{}/{}.yml'.format(base_path, submodule_name)

    def aggregator_config(self):
        return git_aggregator.config.load_config(self.abs_merges_path)[0]

    def get_aggregator(self, **extra_config):
        repo_config = self.aggregator_config()
        repo_config.update(extra_config)
        repo = git_aggregator.repo.Repo(**repo_config)
        repo.cwd = self.abs_path
        return repo

    @classmethod
    def repositories_from_pending_folder(cls, path=None):
        path = path or PENDING_MERGES_DIR
        for root, dirs, files in os.walk(path):
            repo_names = [
                os.path.splitext(fname)[0]
                for fname in files
                if fname.endswith('.yml')
            ]
        return [cls(name) for name in repo_names]

    def has_pending_merges(self):
        found = os.path.exists(self.abs_merges_path)
        if not found:
            return False
        # either empty or commented out
        return bool(self.merges_config())

    def merges_config(self):
        with open(self.abs_merges_path) as f:
            data = yaml.load(f.read()) or {}
            submodule_relpath = os.path.join(os.path.pardir, self.path)
            return data.get(submodule_relpath, {})

    def update_merges_config(self, config):
        # get former config if any
        if os.path.exists(self.abs_merges_path):
            with open(self.abs_merges_path, 'r') as f:
                data = yaml.load(f.read())
        else:
            data = {}
        submodule_relpath = os.path.join(os.path.pardir, self.path)
        data[submodule_relpath] = config
        with open(self.abs_merges_path, 'w') as f:
            yaml.dump(data, f)

    def api_url(self):
        return 'https://api.github.com/repos/{}/{}'.format(
            GIT_C2C_REMOTE_NAME, self.name
        )

    def ssh_url(self, namespace):
        return self.build_ssh_url(namespace, self.name)

    @classmethod
    def build_ssh_url(cls, namespace, repo_name):
        return 'git@github.com:{}/{}.git'.format(namespace, repo_name)


def check_pending_merge_version():
    # First of all, check if there's a migration file at the old path
    if os.path.exists('odoo/pending-merges.yaml'):
        # notify ppl that this file was moved, then terminate execution
        exit_msg(
            '##############################################################\n'
            'Found file `odoo/pending-merges.yaml`.\n'
            'Please run `invoke deprecate.split-pending-merges` task first.\n'
            '##############################################################\n'
        )


def get_target_branch(ctx, target_branch=None):
    """Gets the branch to push on and checks if we're overriding something.

    If target_branch is given only checks for the override.
    Otherwise create the branch name and check for the override.
    """
    current_branch = ctx.run(
        'git symbolic-ref --short HEAD', hide=True
    ).stdout.strip()
    project_id = cookiecutter_context()['project_id']
    if not target_branch:
        commit = ctx.run('git rev-parse HEAD', hide=True).stdout.strip()[:8]
        target_branch = 'merge-branch-{}-{}-{}'.format(
            project_id, current_branch, commit
        )
    if current_branch == 'master' or re.match(r'\d{1,2}.\d', target_branch):
        ask_or_abort(
            'You are on branch {}.'
            ' Please confirm override of target branch {}'.format(
                current_branch, target_branch
            )
        )
    return target_branch


@task
def init(ctx):
    """Add git submodules read in the .gitmodules files.

    Allow to edit the .gitmodules file, add all the repositories and
    run the command once to add all the submodules.

    It means less 'git submodule add -b ... {url} {path}' commands to run

    """
    add_command = 'git submodule add'
    if AUTOSHARE_ENABLED:
        add_command = 'git autoshare-submodule-add'
    gitmodules = build_path('.gitmodules')
    res = ctx.run(
        r"git config -f %s --get-regexp '^submodule\..*\.path$'" % gitmodules,
        hide=True,
    )
    odoo_version = cookiecutter_context()['odoo_version']
    with cd(root_path()):
        for line in res.stdout.splitlines():
            path_key, path = line.split()
            url_key = path_key.replace('.path', '.url')
            url = ctx.run(
                'git config -f {} --get "{}"'.format(gitmodules, url_key),
                hide=True,
            ).stdout
            try:
                ctx.run(
                    '%s -b %s %s %s'
                    % (add_command, odoo_version, url.strip(), path.strip())
                )
            except exceptions.Failure:
                pass

    print("Submodules added")
    print()
    print("You can now update odoo/Dockerfile with this addons-path:")
    print()
    list(ctx)


@task(
    help={
        'dockerfile': 'With --no-dockerfile, the raw paths are listed instead '
        'of the Dockerfile format'
    }
)
def list(ctx, dockerfile=True):
    """List git submodules paths.

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
        lines = (
            line for line in content.splitlines() if line not in blacklist
        )
        lines = chain(lines, ['odoo/src/addons', 'odoo/local-src'])
        lines = ("/%s" % line for line in lines)
        template = "ENV ADDONS_PATH=\"%s\" \\\n"
        print(template % (', \\\n'.join(lines)))
    else:
        print(content)


@task
def merges(ctx, submodule_path, push=True, target_branch=None):
    """Regenerate a pending branch for a submodule.

    Use case: a PR has been updated and you want to refresh it.

    It reads pending-merges.d/sub-name.yml, runs gitaggregator on the submodule
    and pushes the new branch on dynamic target constructed as follows:
    camptocamp/merge-branch-<project_id>-<branch>-<commit>

    By default, the branch is pushed on the camptocamp remote, but you
    can disable the push with ``--no-push``.

    Beware, if you changed the remote of the submodule manually, you still need
    to run `sync_remote` manually.
    """

    check_pending_merge_version()
    repo = Repo(submodule_path)

    target_branch = get_target_branch(ctx, target_branch=target_branch)
    print('Building and pushing to camptocamp/{}'.format(target_branch))
    print()
    aggregator = repo.get_aggregator(
        target={'branch': target_branch, 'remote': GIT_C2C_REMOTE_NAME}
    )
    aggregator.aggregate()

    process_travis_file(ctx, repo)
    if push:
        aggregator.push()


@task
def push(ctx, submodule_path, target_branch=None):
    """Push a Submodule

    Pushes the current state of your submodule to the target remote and branch
    either given by you or specified in pending-merges.yml
    """
    check_pending_merge_version()
    repo = Repo(submodule_path)
    target_branch = get_target_branch(ctx, target_branch=target_branch)
    print('Pushing to camptocamp/{}'.format(target_branch))
    print()
    aggregator = repo.get_aggregator(
        target={'branch': target_branch, 'remote': GIT_C2C_REMOTE_NAME}
    )
    with cd(repo.path):
        aggregator._switch_to_branch(target_branch)
        process_travis_file(ctx, repo)
        aggregator.push()


def process_travis_file(ctx, repo):
    tf = '.travis.yml'
    with cd(repo.abs_path):
        if not os.path.exists(tf):
            print(
                repo.abs_path + tf,
                'does not exists. Skipping travis exclude commit',
            )
            return

        print("Writing exclude branch option in {}".format(tf))
        with open(tf, 'a') as travis:
            travis.write(BRANCH_EXCLUDE)

        cmd = 'git commit {} -m "Travis: exclude new branch from build"'
        commit = ctx.run(cmd.format(tf), hide=True)
        print("Committed as:\n{}".format(commit.stdout.strip()))


@task
def show_prs(ctx, submodule_path=None, state=None):
    """Show all pull requests in pending merges.

    Pass nothing to check all submodules.
    Pass `-s path/to/submodule` to check specific ones.
    """
    check_pending_merge_version()
    logging.getLogger('requests').setLevel(logging.ERROR)
    if submodule_path is None:
        repositories = Repo.repositories_from_pending_folder()
    else:
        repositories = [Repo(submodule_path)]
    if not repositories:
        exit_msg('No repo to check.')

    pr_info_msg = '{shortcut} in state {state} ({merged})'
    all_repos_prs = {}
    for repo in repositories:
        aggregator = repo.get_aggregator()
        print('--')
        print('Checking:', repo.name)
        print('Path:', repo.path)
        print('Merge file:', repo.merges_path)
        all_prs = aggregator.collect_prs_info()
        if state is not None:
            # filter only our state
            all_prs = {k: v for k, v in all_prs.items() if k == state}
        for pr_state, prs in all_prs.items():
            print('State:', pr_state)
            for i, pr_info in enumerate(prs, 1):
                all_repos_prs.setdefault(pr_state, []).append(pr_info)
                print('  {})'.format(i), pr_info_msg.format(**pr_info))
    return all_repos_prs


@task
def show_closed_prs(ctx, submodule_path=None, purge_closed=False):
    """Show all closed pull requests in pending merges.

    Pass nothing to check all submodules.
    Pass `-s path/to/submodule` to check specific ones.
    """
    all_repos_prs = show_prs(
        ctx, submodule_path=submodule_path, state='closed'
    )

    if purge_closed:
        print('Purging closed ones...')
        for closed_pr_info in all_repos_prs.get('closed', []):
            remove_pending(ctx, closed_pr_info['shortcut'])


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
def sync_remote(ctx, submodule_path=None, repo=None, force_remote=False):
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
    check_pending_merge_version()
    assert submodule_path or repo
    repo = repo or Repo(submodule_path)

    if repo.has_pending_merges():
        with open(repo.abs_merges_path) as pending_merges:
            # read everything we can reach
            # for reading purposes only
            data = yaml.load(pending_merges.read())
            submodule_pending_config = data[
                os.path.join(os.path.pardir, repo.path)
            ]
            merges_in_action = submodule_pending_config['merges']
            registered_remotes = submodule_pending_config['remotes']

            if force_remote:
                new_remote_url = registered_remotes[force_remote]
            elif merges_in_action:
                new_remote_url = registered_remotes[GIT_C2C_REMOTE_NAME]
            else:
                new_remote_url = next(
                    remote
                    for remote in registered_remotes.values()
                    if remote != GIT_C2C_REMOTE_NAME
                )
    elif repo.path == 'odoo/src':
        # special way to treat that particular submodule
        if ask_confirmation('Use odoo:odoo instead of OCA/OCB?'):
            new_remote_url = Repo.build_ssh_url('odoo', 'odoo')
        else:
            new_remote_url = Repo.build_ssh_url('OCA', 'OCB')
    else:
        # resolve what's the parent repository from which C2C consolidation
        # one was forked
        response = requests.get(repo.api_url())
        if response.ok:
            info = response.json()
            parent = info.get('parent', {})
            if parent:
                # resolve w/ parent repository
                # C2C consolidation was forked from
                new_remote_url = parent.get('ssh_url')
            else:
                # not a forked repo (eg: camptocamp/connector-jira)
                new_remote_url = info.get('ssh_url')
        else:
            print(
                "Couldn't reach Github API to resolve submodule upstream."
                " Please provide it manually."
            )
            default_repo = repo.name.replace('_', '-')
            new_namespace = input('Namespace [OCA]: ') or 'OCA'
            new_repo = (
                input('Repo name [{}]: '.format(default_repo)) or default_repo
            )
            new_remote_url = Repo.build_ssh_url(new_namespace, new_repo)

    ctx.run(
        'git config --file=.gitmodules submodule.{}.url {}'.format(
            repo.path, new_remote_url
        )
    )
    relative_name = repo.path.replace('../', '')
    with cd(build_path(relative_name)):
        ctx.run('git remote set-url origin {}'.format(new_remote_url))

    print(
        'Submodule {} is now being sourced from {}'.format(
            repo.path, new_remote_url
        )
    )

    if repo.has_pending_merges():
        # we're being polite here, excode 1 doesn't apply to this answer
        ask_or_abort(
            'Rebuild consolidation branch for {}?'.format(relative_name)
        )
        push = ask_confirmation(
            'Push it to `{}\'?'.format(GIT_C2C_REMOTE_NAME)
        )
        merges(ctx, relative_name, push=push)
    else:
        odoo_version = cookiecutter_context()['odoo_version']
        if ask_confirmation(
            'Submodule {} has no pending merges. Update it to {}?'.format(
                relative_name, odoo_version
            )
        ):
            with cd(repo.abs_path):
                os.system('git fetch origin {}'.format(odoo_version))
                os.system('git checkout origin/{}'.format(odoo_version))


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
        try:
            upstream, repo_name, entity_type, entity_id = entity_spec.split(
                '/'
            )[3:7]
        except ValueError:
            exit_msg(
                "Could not parse: {}.\n"
                "Accept formats are either:\n"
                "* Full url: https://github.com/namespace/repo/pull/1234/files#diff-deadbeef\n"
                "* Short ref: remote/repo#pull-request-id".format(entity_spec)
            )

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


def generate_pending_merges_file_template(repo, upstream):
    """Create a submodule merges file from template.

    That should be either `odoo/src` or `odoo/external-src/<module>`
    """
    # could be that this is the first PM ever added to this project
    if not os.path.exists(PENDING_MERGES_DIR):
        os.makedirs(PENDING_MERGES_DIR)

    oca_ocb_remote = False
    if repo.path == 'odoo/src' and upstream == 'odoo':
        oca_ocb_remote = not ask_confirmation(
            'Use odoo:odoo instead of OCA/OCB?'
        )

    remote_upstream_url = repo.ssh_url(upstream)
    remote_c2c_url = repo.ssh_url(GIT_C2C_REMOTE_NAME)
    cc_context = cookiecutter_context()
    odoo_version = cc_context['odoo_version']
    default_target = 'merge-branch-{}-master'.format(cc_context['project_id'])
    remotes = CommentedMap()
    remotes.insert(0, upstream, remote_upstream_url)

    if oca_ocb_remote:
        # use the oca remote as base even if we are adding an
        # odoo/odoo#123 pull request
        remotes.insert(0, 'oca', Repo.build_ssh_url('OCA', 'OCB'))

    if upstream != GIT_C2C_REMOTE_NAME:
        # if origin is not the same: add c2c one
        remotes.insert(0, GIT_C2C_REMOTE_NAME, remote_c2c_url)
    config = CommentedMap()
    config.insert(0, 'remotes', remotes)
    config.insert(
        1, 'target', '{} {}'.format(GIT_C2C_REMOTE_NAME, default_target)
    )
    if oca_ocb_remote:
        base_merge = '{} {}'.format('oca', odoo_version)
    else:
        base_merge = '{} {}'.format(upstream, odoo_version)
    config.insert(2, 'merges', CommentedSeq([base_merge]))
    repo.update_merges_config(config)


def add_pending_pull_request(repo, conf, upstream, pull_id):
    odoo_version = cookiecutter_context().get('odoo_version')
    pending_mrg_line = '{} refs/pull/{}/head'.format(upstream, pull_id)
    if pending_mrg_line in conf.get('merges', {}):
        exit_msg(
            'Requested pending merge is already mentioned in {} '.format(
                repo.abs_merges_path
            )
        )

    response = requests.get('{}/pulls/{}'.format(repo.api_url(), pull_id))

    # TODO: auth
    base_branch = response.json().get('base', {}).get('ref')
    if response.ok:
        if base_branch:
            if base_branch != odoo_version:
                ask_or_abort(
                    'Requested PR targets branch different from'
                    ' current project\'s major version. Proceed?'
                )
    else:
        print(
            'Github API call failed ({}):'
            ' skipping target branch validation.'.format(response.status_code)
        )

    # TODO: handle comment
    # if response.ok:
    #     # probably, wrapping `if` could be an overkill
    #     pending_mrg_comment = response.json().get('title')
    # else:
    #     pending_mrg_comment = False
    #     print('Unable to get a pull request title.'
    #           ' You can provide it manually by editing {}.'.format(
    #               repo.abs_merges_path))

    known_remotes = conf['remotes']
    if upstream not in known_remotes:
        known_remotes.insert(0, upstream, repo.ssh_url(upstream))
    # we're just at the place to append a new pending merge
    # ruamel.yaml's API won't allow ppl to insert items at the end of
    # array, so the closest solution would be to insert it at position 1,
    # straight after `OCA basebranch` merge item.
    conf['merges'].insert(1, pending_mrg_line)


def add_pending_commit(repo, conf, upstream, commit_sha):
    if len(commit_sha) < 40:
        ask_or_abort(
            "You are about to add a patch referenced by a short commit SHA.\n"
            "It's recommended to use fully qualified 40-digit hashes though.\n"
            "Continue?"
        )
    pending_mrg_line = 'git am "$(git format-patch -1 {} -o ../patches)"'.format(
        commit_sha
    )

    if pending_mrg_line in conf.get('shell_command_after', {}):
        exit_msg(
            'Requested pending merge is mentioned in {} already'.format(
                repo.abs_merges_path
            )
        )
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
    check_pending_merge_version()
    # pattern, given an https://github.com/<upstream>/<repo>/pull/<pr-index>
    # # PR headline
    # # PR link as is
    # - refs/pull/<pr-index>/head
    parts = parse_github_url(entity_url)

    upstream = parts.get('upstream')
    repo_name = parts.get('repo_name')
    entity_type = parts.get('entity_type')
    entity_id = parts.get('entity_id')

    repo = Repo(repo_name, path_check=False)
    if not os.path.exists(repo.abs_merges_path):
        generate_pending_merges_file_template(repo, upstream)

    conf = repo.merges_config()
    # TODO: adding comments doesn't really work :/
    if entity_type == 'pull':
        add_pending_pull_request(repo, conf, upstream, entity_id)
    elif entity_type in ('commit', 'tree'):
        add_pending_commit(repo, conf, upstream, entity_id)

    # write back a file
    repo.update_merges_config(conf)
    sync_remote(ctx, repo=repo)


def remove_pending_commit(repo, conf, upstream, commit_sha):
    line_to_drop = 'git am "$(git format-patch -1 {} -o ../patches)"'.format(
        commit_sha
    )
    if line_to_drop not in conf.get('shell_command_after', {}):
        exit_msg(
            'No such reference found in {},'
            ' having troubles removing that:\n'
            'Looking for: {}'.format(repo.abs_merges_path, line_to_drop)
        )
    conf['shell_command_after'].remove(line_to_drop)
    if not conf['shell_command_after']:
        del conf['shell_command_after']


def remove_pending_pull(repo, conf, upstream, pull_id):
    line_to_drop = '{} refs/pull/{}/head'.format(upstream, pull_id)
    if line_to_drop not in conf['merges']:
        exit_msg(
            'No such reference found in {},'
            ' having troubles removing that:\n'
            'Looking for: {}'.format(repo.abs_merges_path, line_to_drop)
        )
    conf['merges'].remove(line_to_drop)


@task
def remove_pending(ctx, entity_url):
    """Remove a pending merge using given entity link"""

    check_pending_merge_version()
    parts = parse_github_url(entity_url)

    upstream = parts.get('upstream')
    repo_name = parts.get('repo_name')
    repo = Repo(repo_name)
    entity_type = parts.get('entity_type')
    entity_id = parts.get('entity_id')

    config = repo.merges_config()
    if entity_type == 'pull':
        remove_pending_pull(repo, config, upstream, entity_id)
    elif entity_type in ('tree', 'commit'):
        remove_pending_commit(repo, config, upstream, entity_id)

    # check if that file is useless since it has an empty `merges` section
    # if it does - drop it instead of writing a new file version
    # only the upstream branch is present in `merges`
    # first item is `- oca 11.0` or similar
    pending_merges_present = len(config['merges']) > 1
    patches = len(config.get('shell_command_after', {}))

    if not pending_merges_present and not patches:
        os.remove(repo.abs_merges_path)
        sync_remote(ctx, repo=repo)
    else:
        repo.update_merges_config(config)
