# Odoo Project Tools

[![pre-commit](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml)
[![tests](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)


## Installation
This repository contains helper tasks for working with Camptocamp Odoo projects.

Install with [pipx](https://pypa.github.io/pipx/):


    pipx install git+https://github.com/camptocamp/odoo-project-tools.git


You may need to have some build dependencies installed:

    sudo apt install pipx git libpq-dev gcc python3-dev

## Usage

Note: information below is subject to change.


The package brings the following commands.


`otools-project`: manage proj

`otools-pending`: manage pendng merges

`otools-release`: bump releases

`otools-addon`: tools to work with addons and test requirements

`otools-tasks`: access to the "old" invoke tasks, yet to be rewritten

`otools-ba`: tools for functional people, see [documentation](docs/otools-ba.md).

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

Run `otools-release release --help` to know more about the options.


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

## Project conversion

Create a new checkout of the project you are working on, with the submodules
up-to-date (you will need to start an instance later in the process to get the
installed addons, and at that stage of the conversion, the project will not be
runnable yet).

Go to the root of your project and follow the steps below:

1. Make a copy of your local docker-compose.override.yml file:

    ```
    mv docker-compose.override.yml docker-compose.override.yml.bak
    ```

2. Run sync from Vincent's fork of odoo-template

    ```
    invoke project.sync --version core-image
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

5. Install conversion tools

    ```
    pip install "odoo-tools[convert] @ git+https://github.com/camptocamp/odoo-project-tools.git"
    ```

    or, if you're using pipx:

    ```
    pipx inject odoo-tools "odoo-tools[convert] @ git+https://github.com/camptocamp/odoo-project-tools.git"
    ```

6. Run the conversion script

    ```
    otools-conversion
    ```

    The script will move things around, remove some of the submodules (odoo/src,
    odoo/external-src/enterprise and odoo/external-src/odoo-cloud-platform), and
    when done display a message about what further manual steps are required, and
    what you need to check for. These steps will also be saved to a file (see step 9 below).

    Be careful, if you need to redo these steps, the submodules will have
    been removed by the script, you will need to run `git submodule update -i` again.

7.  Install pre-commit and run it on all files

    ```
    pre-commit install
    pre-commit run --all-files
    ```
    Manually fix the issues that pre-commit is unable to fix by itself

8.  Stage all changes and commit

    ```
    git add .
    git commit -m "Convert to proj v2"
    ```

9.  Follow the steps in the generated `V2_MIG_NEXT_STEPS.todo` file
