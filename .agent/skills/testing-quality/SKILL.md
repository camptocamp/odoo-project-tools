# Testing & Quality Checks Skill

## Purpose
Run test suites with pytest, check code quality with pre-commit, and enforce minimum coverage standards for changes to the odoo-project-tools repository.

## Quick Reference

### Run All Tests
```bash
uv run pytest --verbose
```

### Run Specific Test File
```bash
uv run pytest tests/test_release.py -q
uv run pytest tests/test_addon_add.py::test_addon_add_basic -v
```

### Run Quality Checks
```bash
pre-commit run -a
```

### Run Specific Pre-commit Hook
```bash
pre-commit run ruff --all-files
pre-commit run black --all-files
```

### Check Test Coverage
```bash
uv run pytest --cov=odoo_tools tests/
```

## Test Organization

Tests are organized by functional area:

| Test File | Purpose |
|-----------|---------|
| [test_project.py](tests/test_project.py) | Project initialization and config |
| [test_release.py](tests/test_release.py) | Release process, versioning, changelog |
| [test_addon_*.py](tests/) | Addon management operations |
| [test_cloud.py](tests/test_cloud.py) | Cloud platform interactions |
| [test_utils_*.py](tests/) | Utility module functions |

## Test Fixtures and Markers

### project_setup Marker
Use `@pytest.mark.project_setup()` to create fake Odoo project scaffolding:

```python
@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0"),
    proj_version="16.0.1.1.0",
)
@pytest.mark.usefixtures("project")
def test_my_command(project):
    # Tests run in isolated filesystem with fake project
    pass
```

See [tests/conftest.py](tests/conftest.py) for available markers and fixtures.

### Click CliRunner
All CLI tests use Click's test runner:

```python
def test_cli_command(runner):
    from odoo_tools.cli.addon import addon
    result = runner.invoke(addon, ['list'])
    assert result.exit_code == 0
```

## Quality Check Rules

Pre-commit enforces:

1. **Ruff (linting & formatting)**: Python 3.10+ compatibility, pathlib usage, line length 88
2. **Black (code formatting)**: Consistent code style
3. **AGPL headers**: All Python files must have license header
4. **Import sorting**: Organized imports
5. **YAML validation**: Valid YAML in config files
6. **File permissions**: Correct permissions for executable scripts

Run `git diff --cached` to preview changes before committing.

## Test Coverage Expectations

| Change Type | Minimum Coverage |
|-------------|-----------------|
| Bug fix | 100% of changed code |
| New feature | 80%+ of new code |
| Documentation | N/A |
| Refactoring | Match existing coverage |

## Common Test Patterns

### Testing CLI Commands
```python
def test_release_command(runner, project):
    from odoo_tools.cli.release import release
    result = runner.invoke(release, ['bump', '--help'])
    assert result.exit_code == 0
    assert "--new-version" in result.output
```

### Testing Utilities
```python
def test_config_reload():
    from odoo_tools.utils.config import config
    config._reload()
    assert config.project_root is not None
```

### Testing with Project State
```python
@pytest.mark.project_setup(manifest=dict(odoo_version="16.0"))
def test_addon_list(runner, project):
    from odoo_tools.cli.addon import addon
    result = runner.invoke(addon, ['list'])
    assert result.exit_code == 0
    config._reload()  # Reload if config was modified
```

## Performance Testing

For long-running operations:
```bash
# Run with timeout
timeout 30s uv run pytest tests/test_cloud.py -v

# Run with specific markers
uv run pytest -m "not slow" tests/
```

## Debugging Failed Tests

1. **Show print output**: `uv run pytest -s tests/test_file.py`
2. **Drop into debugger**: Add `import pdb; pdb.set_trace()` in test code
3. **Run with verbose output**: `uv run pytest -vv --tb=long tests/`
4. **Check isolated filesystem**: `runner.isolated_filesystem()` mounts tests in temp directory

## CI/CD Integration

The repository uses GitHub Actions workflows:

- **pre-commit.yml**: Runs linting on every push
- **test.yml**: Runs full test suite on PRs
- **release.yml**: Automated release workflow (when tagged)

Note: Pre-commit must pass before CI runs tests. Fix locally with `pre-commit run -a` first.

## Related Skills

- [Development Environment Setup](../dev-environment-setup/SKILL.md) - Configure dev environment
- [CLI Development](../cli-development/SKILL.md) - Writing Click CLI commands with tests
- [Release Management](../release-management/SKILL.md) - Release process and commitments
