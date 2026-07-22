# Project Guidelines

## Code Style

- Use Python 3.10+ and follow formatting/lint rules from [pyproject.toml](../pyproject.toml).
- Keep line length at 88 and write code compatible with Ruff rules configured in [pyproject.toml](../pyproject.toml).
- Keep existing file headers and AGPL license notices in Python files.
- Prefer `pathlib` patterns over `os.path` when possible (the lint config enforces this).

## Architecture

- CLI commands live under [odoo_tools/cli](../odoo_tools/cli) and are thin orchestration layers.
- Reusable business and integration logic lives in [odoo_tools/utils](../odoo_tools/utils). Put new shared behavior there, not directly in CLI modules.
- [odoo_tools/tasks](../odoo_tools/tasks) contains legacy invoke tasks. Prefer the Click-based CLI modules for new work.
- Tests are pytest-based in [tests](../tests), with Click runner fixtures and project bootstrap helpers in [tests/conftest.py](../tests/conftest.py) and [tests/common.py](../tests/common.py).

## Build And Test

- Install dev dependencies with `uv sync --dev --all-extras`.
- Run tests with `uv run pytest --verbose`.
- Run quality checks with `pre-commit run -a`.
- Build distributions with `python3 -m build`.
- Prefer running targeted tests first (for example `uv run pytest tests/test_release.py -q`) before full-suite runs.

## Project Conventions

- Use the `project_setup` pytest marker for tests that require fake project scaffolding (see [tests/conftest.py](../tests/conftest.py)).
- If a test writes project config files, reload config state with `config._reload()` and clear cached project manifest lookups when relevant.
- Keep changelog fragments in [changes.d](../changes.d) and rely on Towncrier config from [pyproject.toml](../pyproject.toml).
- Follow the release process in [Releasing.md](../Releasing.md) rather than ad-hoc tagging/build steps.

## Documentation Links

- Core usage and command overview: [README.md](../README.md)
- Functional BA workflow: [docs/otools-ba.md](../docs/otools-ba.md)
- Pull request test workflow: [docs/otools-pr.md](../docs/otools-pr.md)
- Release checklist: [Releasing.md](../Releasing.md)
