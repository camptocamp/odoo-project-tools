# Odoo Project Tools

[![pre-commit](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml)
[![tests](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

## Installation

This repository contains helper tasks for working with Camptocamp Odoo projects.

Install with [pipx](https://pypa.github.io/pipx/):


    pipx install git+https://github.com/camptocamp/odoo-project-tools


You may need to have some build dependencies installed:

    sudo apt install pipx git libpq-dev gcc python3-dev

## Usage

Note: information below is subject to change.


The package brings the following commands.


`otools-project`: manage project

`otools-pending`: manage pending merges

`otools-release`: bump releases

`otools-addon`: tools to work with addons and test requirements

`otools-submodule`: manage submodules

`otools-tasks`: access to the "old" invoke tasks, yet to be rewritten

`otools-ba`: tools for functional people, see [documentation](docs/otools-ba.md).

`otools-pr`: tools to test pull request on a local odoo running a database dump, see [documentation](docs/otools-pr.md).

`otools-db`: tools to manage local databases

`otools-cloud`: tools to interact with the cloud platform

Use `--help` to get the list of subcommands.


### otools-project

Use the `init` command to initialize a new project to use these tools.

Example:

    ```
    PROJ_TMPL_VER=1 otools-project init
    ```

This will create all configuration files that must be added to the project.


### otools-pending

Tool for managing pending merges and performing git aggregations on repositories.
It includes commands for listing pull requests,
aggregating branches, and adding or removing pending merges.

Commands:
    - `show`: List pull requests for specified repositories or all repositories
      in the pending folder. Supports filtering by state and purging closed or
      merged pull requests.
    - `aggregate`: Perform a git aggregation on a specified repository and push
      the result to a remote branch if desired.
    - `add`: Add a pending merge using a given entity URL. Optionally, run git
      aggregation or add a patch to the pending merge.
    - `remove`: Remove a pending merge using a given entity URL. Optionally, run
      git aggregation after removal.

Run `otools-pending $cmd --help` to know more about the options.

### otools-release

Tool for preparing a release.

It takes care of:

* bumping the version
* update changelog
* update migration file

Run `otools-release bump --help` to know more about the options.


### otools-addon

NOTE: this tool is meant to be used mostly for future project versions
where we'll have all modules installed via pip.

The most handy feature at the moment is: `otools-addon add-req`.

It allows to add requiments and test requirements on the fly to an existing req file.

Example:

    ```
    otools-addon add-req edi_oca -v 18 -p $pr_ref -f test-requirements.txt
    ```

This will add the test dependency in the right way to the given file.

### otools-db

```
Usage: otools-db [OPTIONS] COMMAND [ARGS]...

  Database management commands.

Options:
  --debug
  --help   Show this message and exit.

Commands:
  dump           Create a PostgreSQL dump of the specified database.
  list           List all databases in the container.
  list-versions  Print a table of DBs with Marabunta version and install...
  restore        Restore a PostgreSQL dump to a database.
```

### otools-cloud

Tools to interact with the cloud platform.

#### otools-cloud dump

Tools to interact with the cloud platform database dumps.

```
Usage: otools-cloud dump [OPTIONS] COMMAND [ARGS]...

  Cloud platform dump management commands.

Options:
  --help  Show this message and exit.

Commands:
  create             Generate a new dump on the cloud platform.
  download           Download a dump from the cloud platform.
  list               List available dumps on the cloud platform.
  restore            Restore an uploaded dump on the cloud platform.
  upload             Upload a dump file to the cloud platform.
```

##### Download a dump and restore it locally

```
otools-cloud dump download --env prod --restore-to-db odoodb
```

Optionally, specify exactly the dump to download:

```
otools-cloud dump download --env prod --name celebrimbor-database-name.pg.gpg --restore-to-db odoodb
```

##### Dump a local database and upload it to the cloud platform

```
otools-cloud dump upload --from-db odoodb --env labs.my-lab
```

## Project conversion

Create a new checkout of the project you are working on, with the submodules up-to-date.

Go to the root of your project and follow the steps below:

1. Make a copy of your local docker-compose.override.yml file:

    ```
    mv docker-compose.override.yml docker-compose.override.yml.bak
    ```

2. Run sync from odoo-template using the `core_image` version.

    ```
    invoke project.sync --version core_image
    ```

3. Initialize the project at v1

    ```
    PROJ_TMPL_VER=1 otools-project init
    ```

4. Stage new files and commit

    ```
    git add .
    git commit -m "Initialize project v1"
    ```

    You can always reset hard to this commit when trying the conversion to v2
    ;) (don't forget to update the project submodules again, as they will
    certainly have been reset)

5. Run the conversion script

    ```
    otools-conversion
    ```

    The script will move things around, remove some of the submodules (odoo/src,
    odoo/external-src/enterprise and odoo/external-src/odoo-cloud-platform), and
    when done display a message about what further manual steps are required, and
    what you need to check for. These steps will also be saved to a file (see step 9 below).

    Be careful, if you need to redo these steps, the submodules will have
    been removed by the script, you will need to run `git submodule update -i` again.

6.  Install pre-commit and run it on all files

    ```
    pre-commit install
    pre-commit run --all-files
    ```
    Manually fix the issues that pre-commit is unable to fix by itself

7.  Stage all changes and commit

    ```
    git add .
    git commit -m "Convert to proj v2"
    ```

8.  Follow the steps in the generated `V2_MIG_NEXT_STEPS.todo` file
