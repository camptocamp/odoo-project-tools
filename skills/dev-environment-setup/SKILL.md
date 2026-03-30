---
name: dev-environment-setup
description: Set up and validate a working development environment for odoo-project-tools using uv, Python, and project quality tooling. Use when preparing a machine or troubleshooting local setup issues.
---

# Development Environment Setup Skill

## Purpose
Configure and manage the development environment for odoo-project-tools using uv, ensure dependencies are installed, and validate the environment is ready for development.

## Quick Reference

### Install Development Dependencies
```bash
uv sync --dev --all-extras
```
This installs all dependencies including dev tools (pytest, pre-commit, etc.) and optional extras.

### Verify Environment
```bash
python3 --version  # Should be 3.10+
pip list | grep -E 'odoo-tools|pytest|ruff|pre-commit'
```

### Activate Environment
```bash
source ./build-venv/bin/activate  # If using venv
# or use uv commands directly: uv run pytest ...
```

### Build Check
```bash
python3 -m build
```

## Key Configuration Files

- **pyproject.toml**: Project metadata, dependencies, tool configurations (Ruff, pytest, Black, etc.)
- **Ruff config**: Enforces Python 3.10+ compatibility, line length 88, pathlib usage, AGPL headers
- **.pre-commit-config.yaml**: Git hooks for linting and formatting before commits

## Environment Requirements

- **Python 3.10+**: Minimum required version (enforced by Ruff linting)
- **uv**: Package installer and task runner (recommended over pip/venv directly)
- **System dependencies**: `libpq-dev`, `gcc`, `python3-dev` (for psycopg2, docker, etc.)

## Common Setup Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'odoo_tools'` | Run `uv sync --dev --all-extras` in project root |
| Pre-commit hook failures | Run `pre-commit run -a` to see linting errors before committing |
| Docker-related imports fail | Install docker: `pip install docker` or ensure Docker daemon runs |
| psycopg2 compilation fails | Install `libpq-dev` (Linux) or use `psycopg2-binary` |

## Development Workflow

1. **Setup**: `uv sync --dev --all-extras`
2. **Make changes**: Follow [Code Style](#code-style) rules
3. **Test locally**: `uv run pytest tests/ -q`
4. **Check quality**: `pre-commit run -a`
5. **Run full test suite**: `uv run pytest --verbose`
6. **Build distribution**: `python3 -m build`

## Code Style

- **Line length**: 88 characters (Ruff enforced)
- **Import style**: Prefer `pathlib` over `os.path`
- **Type hints**: Use where possible for better IDE support
- **Headers**: AGPL license header in all Python files
- **Formatter**: Follows Ruff rules configured in pyproject.toml

## Testing Environment Isolation

Each test should:
- Use Click's `CliRunner` with `isolated_filesystem()` for file operations
- Use the `@pytest.mark.project_setup` marker for fake Odoo project scaffolding
- Call `config._reload()` after creating project config files
- Clean up database lookups when testing project manifest operations

See [tests/conftest.py](tests/conftest.py) and [tests/common.py](tests/common.py) for fixtures and helpers.

## Related Skills

- [Release Management](../release-management/SKILL.md) - Building and releasing distributions
- [Testing & Quality Checks](../testing-quality/SKILL.md) - Running test suites and pre-commit
- [CLI Development](../cli-development/SKILL.md) - Building Click-based CLI commands
