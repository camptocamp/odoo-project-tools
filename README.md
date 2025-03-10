# Odoo Project Tools

[![pre-commit](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml)
[![tests](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)


## Installation
This repository contains helper tasks for working with Camptocamp Odoo projects.

Create a virtual environment and activate it, then run:

```
pip install --user git+https://github.com/camptocamp/odoo-project-tools.git
```

If you use  [pipx](https://pypa.github.io/pipx/) then you can run instead:

```
pipx install git+https://github.com/camptocamp/odoo-project-tools.git
```

## Usage

Note: information below is subject to change.


The package brings the following commands:


`otools-project`: manage proj

`otools-addons`: tools to work with addons

`otools-release`: bump releases

`otools-tasks`: access to the "old" invoke tasks, being rewritten.


Use `--help` to get the list of subcommands.

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
