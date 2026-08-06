# CLI Development Skill

## Purpose
Develop new Click-based command-line interfaces following odoo-project-tools architecture: placing thin orchestration layers in `odoo_tools/cli/` and reusable business logic in `odoo_tools/utils/`.

## Architecture Overview

### Directory Structure
```
odoo_tools/
├── cli/              # Thin CLI orchestration layer
│   ├── addon.py      # Click commands for addon operations
│   ├── release.py    # Release command orchestration
│   ├── project.py    # Project init and config
│   └── ...
├── utils/            # Reusable business and integration logic
│   ├── addon.py      # Addon-related utility functions
│   ├── config.py     # Configuration loading and management
│   ├── pkg.py        # Package/version utilities
│   ├── git.py        # Git operations
│   └── ...
└── exceptions.py     # Shared exception classes
```

### Design Principle
- **CLI layer** (`cli/`): Argument parsing, output formatting, user interaction
- **Utility layer** (`utils/`): Business logic, reusable across CLI and tests
- Clear separation enables testable, reusable code

## Creating a New Command

### 1. Write Business Logic in Utils

Create or extend a utility module in `odoo_tools/utils/`:

```python
# odoo_tools/utils/myfeature.py
# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

def perform_operation(param1, param2):
    """Perform the core operation."""
    # Business logic here
    return result
```

### 2. Create CLI Command

Add Click command in `odoo_tools/cli/`:

```python
# odoo_tools/cli/myfeature.py
# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click

from ..utils.myfeature import perform_operation


@click.group()
def myfeature():
    """Group description for otools-myfeature."""
    pass


@myfeature.command()
@click.option("--param1", required=True, help="Description of param1")
@click.option("--param2", default="default", help="Description of param2")
def subcommand(param1, param2):
    """Subcommand description."""
    result = perform_operation(param1, param2)
    click.echo(f"Success: {result}")
```

### 3. Register Command in Entry Points

Edit `pyproject.toml`:

```toml
[project.scripts]
otools-myfeature = "odoo_tools.cli.myfeature:myfeature"
```

### 4. Write Tests

Create test in `tests/test_myfeature.py`:

```python
import pytest
from click.testing import CliRunner

@pytest.fixture
def runner():
    """Click test runner with isolated filesystem."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        yield runner

def test_myfeature_subcommand(runner):
    from odoo_tools.cli.myfeature import myfeature

    result = runner.invoke(myfeature, ['subcommand', '--param1', 'value'])
    assert result.exit_code == 0
    assert "Success" in result.output
```

## Click Best Practices

### Command Structure

```python
@click.group()
@click.option("--debug", is_flag=True)
@click.pass_context
def mycli(ctx, debug):
    """Main command group."""
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug


@mycli.command()
@click.argument("name")
@click.option("--force", is_flag=True, help="Force operation")
@click.option("--output", type=click.Path(), help="Output file")
@click.pass_context
def subcommand(ctx, name, force, output):
    """Subcommand description."""
    if ctx.obj.get('debug'):
        click.echo("Debug mode: ON")

    # Use context for accessing parent command's data
    click.echo(f"Processing: {name}")
```

### Output Handling

```python
# Simple messages
click.echo("Standard output")
click.secho("Colored output", fg='green')

# Error handling
click.secho("Error occurred", fg='red', err=True)

# Asking for confirmation
if click.confirm("Continue?"):
    click.echo("Continuing...")

# Showing progress
with click.progressbar(items) as bar:
    for item in bar:
        process(item)
```

### Error Handling

```python
from ..exceptions import ProjectConfigException

@mycommand.command()
def operation():
    try:
        result = risky_operation()
    except ProjectConfigException as e:
        click.secho(f"Configuration error: {e}", fg='red', err=True)
        raise SystemExit(1)
    except Exception as e:
        click.secho(f"Unexpected error: {e}", fg='red', err=True)
        raise SystemExit(2)
```

## Importing from Utils

Use relative imports in CLI modules:

```python
# Good
from ..utils.config import config
from ..utils.pkg import get_version
from ..exceptions import ProjectConfigException

# Poor
import odoo_tools.utils.config as config  # Too verbose
```

## Type Hints

Follow PEP 484 for better IDE support:

```python
def perform_operation(param1: str, param2: int) -> dict:
    """Perform operation with type hints."""
    return {"status": "success", "param1": param1}
```

## Code Style Compliance

All CLI code must pass `ruff check` and `pre-commit`:

```bash
# Check before committing
pre-commit run ruff --files odoo_tools/cli/myfeature.py

# Format if needed
ruff format odoo_tools/cli/myfeature.py
```

Rules enforced:
- Line length: 88 characters
- Python 3.10+ only syntax
- Pathlib for paths (use `from pathlib import Path`)
- AGPL header required
- No unused imports

## Testing CLI Commands

### Test File Template

```python
# tests/test_myfeature.py
# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import pytest
from click.testing import CliRunner


@pytest.fixture()
def runner():
    runner = CliRunner()
    with runner.isolated_filesystem():
        yield runner


def test_myfeature_help(runner):
    from odoo_tools.cli.myfeature import myfeature

    result = runner.invoke(myfeature, ['--help'])
    assert result.exit_code == 0
    assert "subcommand" in result.output


@pytest.mark.project_setup  # If needs fake project
def test_myfeature_with_project(runner, project):
    from odoo_tools.utils.config import config
    from odoo_tools.cli.myfeature import myfeature

    result = runner.invoke(myfeature, ['subcommand', '--param1', 'test'])
    assert result.exit_code == 0
```

## Integration with Project Config

Many commands interact with project configuration:

```python
from ..utils.config import config


@mycommand.command()
def operation():
    """Operation using project config."""
    # config is loaded automatically from .odoo_tools/manifest.yml
    odoo_version = config.odoo_version
    project_root = config.project_root

    click.echo(f"Operating in Odoo {odoo_version} project")
```

## Useful Utility Modules

| Module | Purpose |
|--------|---------|
| [utils/config.py](../odoo_tools/utils/config.py) | Load/reload project configuration |
| [utils/git.py](../odoo_tools/utils/git.py) | Git operations (branches, commits, etc.) |
| [utils/os_exec.py](../odoo_tools/utils/os_exec.py) | Execute external commands safely |
| [utils/path.py](../odoo_tools/utils/path.py) | Path utilities with Pathlib |
| [utils/pkg.py](../odoo_tools/utils/pkg.py) | Package/version functions |
| [exceptions.py](../odoo_tools/exceptions.py) | Standard exception types |

## Documentation

Add help text to all commands and options:

```python
@mycommand.command()
@click.argument("name", help="Name of the resource")  # Argument description
@click.option("--force", is_flag=True, help="Force without confirmation")
def operation(name, force):
    """Full description of what this command does.

    Include examples if the command is complex:

    \b
    Examples:
        otools-mycommand operation --name foo --force
    """
```

## Debugging Commands

Run commands in isolation during development:

```bash
# Direct Python invocation
python3 -c "from odoo_tools.cli.myfeature import myfeature; myfeature(['--help'])"

# Via uv
uv run otools-myfeature --help

# With debug output
PYTHONVERBOSE=1 otools-myfeature operation --debug
```

## Related Skills

- [Development Environment Setup](../dev-environment-setup/SKILL.md) - Dev environment
- [Testing & Quality Checks](../testing-quality/SKILL.md) - Testing CLI code
- [Project Setup & Initialization](../project-setup-initialization/SKILL.md) - Example: project init command
