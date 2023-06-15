# Odoo Project Tools

This repository contains helper tasks for working with Camptocamp Odoo projects.

## Installation

Create a virtual environment and activate it, then

```
pip install git+ssh://git@github.com/camptocamp/odoo-project-tools#egg=odoo-tools
```


## Usage

Note: information below is subject to change.


The package brings the following commands:


`otools-project init`: initialize a new project

`otools-addons`: tools to work with addons

Commands:

Usage: otools-addon add [OPTIONS] NAME

  Update project requirements for a given package (odoo or not).

  * Check the latest version of the module on pypi and use that version if
  new.
  * If the module is already present in the requirements.txt file:
    * if the version is the same, do nothing. Otherwise, prompt the user
    * if the addon is present as a PR, prompt the user

Options:
  -v, --version TEXT
  -p, --pr TEXT
  -r, --root-path TEXT
  -o, --odoo BOOLEAN
  --upgrade
  --help                Show this message and exit.
  add  Update project requirements for a given package (odoo or not).


`otools-tasks`: access to the "old" invoke tasks, being rewritten. use `--help` to get a list.
