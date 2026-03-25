# Odoo Project Tools

[![pre-commit](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/pre-commit.yml)
[![tests](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml/badge.svg)](https://github.com/camptocamp/odoo-project-tools/actions/workflows/test.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

## Installation

This repository contains helper tasks for working with Camptocamp Odoo projects.

Install with [uv](https://docs.astral.sh/uv/) (recommended):

    uv tool install git+https://github.com/camptocamp/odoo-project-tools

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

`otools-ba`: tools for functional people, see [documentation](docs/otools-ba.md).

`otools-pr`: tools to test pull request on a local odoo running a database dump, see [documentation](docs/otools-pr.md).

`otools-db`: tools to manage local databases

`otools-cloud`: tools to interact with the cloud platform

`otools-i18n`: tools to manage internationalization (i18n)

`otools-password`: tools to manage admin passwords and LastPass entries

Use `--help` to get the list of subcommands.


### otools-project

Use the `init` command to initialize a new project to use these tools.

Example:

    otools-project init

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

Tools to work with addons and test requirements.

```
Usage: otools-addon [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  add-req  Generate a python requirement line.
  where    Locate an addon by name across the project's addon directories.
```

#### otools-addon add-req

```
Usage: otools-addon add-req [OPTIONS] NAME

  Generate a python requirement line.

  You can simply copy the output and paste it in a requirements.txt file or
  pass the --file option to append it to a file.

  Example for a simple requirement line:

      otools-addon add-req edi_oca -v 18 -f dev-requirements.txt

  Example for a PR:

      otools-addon add-req edi_oca -v 18 -p $pr_ref -f test-requirements.txt

Options:
  -v, --version TEXT
  -p, --pr TEXT
  -b, --branch TEXT
  -r, --repo-name TEXT
  -u, --upstream TEXT
  -f, --file TEXT       file to add the requirement to
  --odoo / --no-odoo    use --no-odoo to install a python module which is not
                        an Odoo addon
  --help                Show this message and exit.
```

#### otools-addon where

```
Usage: otools-addon where [OPTIONS] NAME

  Locate an addon by name across the project's addon directories.

Options:
  --help  Show this message and exit.
```

### otools-db

```
Usage: otools-db [OPTIONS] COMMAND [ARGS]...

  Database management commands.

Options:
  --debug
  --help   Show this message and exit.

Commands:
  addons         Addons management commands.
  dump           Create a PostgreSQL dump of the specified database.
  list           List all databases in the container.
  list-versions  Print a table of DBs with Marabunta version and install...
  restore        Restore an odoo backup locally (sql, dump or zip archive)
```

#### otools-db addons list

List installed addons in the database.

```
otools-db addons list
otools-db addons list --database mydb
otools-db addons list --json
```

By default, it queries the `odoodb` database and displays a rich table with name, title, and version columns. Use `--json` for machine-readable output.

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

### otools-i18n

Tools to manage internationalization (i18n).

```
Usage: otools-i18n [OPTIONS] COMMAND [ARGS]...

  Internationalization (i18n) commands.

Options:
  --help  Show this message and exit.
```

#### Export translation files

```
otools-i18n export odoo/addons/module1 odoo/addons/module2 --languages fr_FR,de_DE
```

This will export the translation files for the given modules and languages.

The `--export-pot` option can be used to also export the pot file for the given modules.

### otools-password

Tools to manage admin passwords and LastPass entries.

```
Usage: otools-password [OPTIONS] COMMAND [ARGS]...

  Password management tools.

Options:
  --debug
  --help   Show this message and exit.

Commands:
  generate-admin-password  Generate a random admin password and initialize it into songs.
```

#### Generate an admin password

```
otools-password generate-admin-password
```

This generates a random password, encrypts it with pbkdf2_sha512, and replaces
the `__GENERATED_ADMIN_PASSWORD__` placeholder in `odoo/songs/install/pre.py`.

#### Generate and store in LastPass

```
otools-password generate-admin-password --store-in-lastpass
```

This does the same as above, and additionally creates two entries in LastPass
(prod and integration) under the `Shared-C2C-Odoo-External/` folder.
Requires the `lpass` CLI to be installed and authenticated.
