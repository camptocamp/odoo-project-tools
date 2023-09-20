# Odoo Project Tools

[![pre-commit](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml)
[![tests](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)


## Installing

### Installing with pip

```
pip install --user git+https://github.com/camptocamp/odoo-project-tools.git
```

### Installing with [pipx](https://pypa.github.io/pipx/)

```
pipx install git+https://github.com/camptocamp/odoo-project-tools.git
```

## Usage

TODO

## Project conversion

Go to the root of your project and follow the steps below:

1. Run sync from Vincent's fork of odoo-template

    ```
    invoke project.sync --fork vrenaville/odoo-template --version mig_to_core
    ```

2. Initialize the project at v1

    ```
    PROJ_TMPL_VER=1 otools-project init
    ```

3. Stage new files and commit

    ```
    git add .
    git commit -m "Initialize project v1"
    ```

    You can always reset hard to this commit when trying the conversion to v2 ;)

4. Install conversion tools

    ```
    pip install "odoo-tools[convert] @ git+https://github.com/camptocamp/odoo-project-tools.git"
    ```

    or, if you're using pipx:

    ```
    pipx inject odoo-tools "odoo-tools[convert] @ git+https://github.com/camptocamp/odoo-project-tools.git"
    ```

5. Start a local instance with a copy of the production database

6. Run the conversion script

    ```
    CONV_ADMIN_PWD=admin otools-conversion -p 8069
    ```

    The script will move things around, figure out which OCA addons are installed
    on your instance, and when done display a message about what further manual
    steps are required, and what you need to check for.

7. Stage all changes and commit

    ```
    git add .
    git commit -m "Convert to proj v2"
    ```

8. Follow the steps in the generated `V2_MIG_NEXT_STEPS.todo` file
