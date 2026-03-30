---
name: project-setup-initialization
description: Initialize and configure Odoo projects with otools-project and manifest settings. Use when creating a new project or fixing project bootstrap/configuration issues.
---

# Project Setup & Initialization Skill

## Purpose
Initialize new Odoo projects with odoo-project-tools, configure project manifests, and set up the necessary configuration files for development, testing, and deployment workflows.

## Quick Reference

### Initialize a New Project
```bash
otools-project init
```

This creates all configuration files needed by the project tools.

### View Project Configuration
```bash
cat .odoo_tools/manifest.yml
```

### Reload Project Configuration
```bash
# In Python code
from odoo_tools.utils.config import config
config._reload()
```

## Project Structure

After initialization, your project contains:

```
my-project/
├── .odoo_tools/
│   ├── manifest.yml          # Project configuration (version, Odoo version, etc.)
│   ├── .bumpversion.cfg      # Version bump configuration
│   └── ...
├── .pre-commit-config.yaml   # Git hooks for quality checks
├── pyproject.toml            # Python project config (if Python-based)
├── addons/                   # Addon modules
│   ├── addon1/
│   ├── addon2/
│   └── ...
├── external/                 # External addon repositories
├── pending/                  # Pending merge branches
├── migrations/               # Marabunta migration files (optional)
└── README.md
```

## Configuration File: .odoo_tools/manifest.yml

The main project configuration file:

```yaml
# .odoo_tools/manifest.yml
project_name: "My Odoo Project"
odoo_version: "16.0"               # Odoo version (14.0, 15.0, 16.0, 17.0, 18.0, etc.)
project_version: "16.0.1.0.0"      # Project version (MAJOR.MINOR.PATCH[.BUILD])
repo_name: "my-odoo-repo"          # Repository name
custom_folder: "custom"            # Path to custom addons (often "addons")
external_folder: "external"        # Path to external repos
pending_folder: "pending"          # Path to pending merges
marabunta_mig_file_rel_path: "migrations/16.0.1.0.0.yml"  # Migration file (optional)

# Optional: Cloud platform config
cloud:
  project_id: "my-cloud-project"
  database_name: "my_database"

# Optional: Database settings
database:
  name: "my_database"
  host: "localhost"
  port: 5432
```

### Key Configuration Fields

| Field | Required | Purpose |
|-------|----------|---------|
| `project_name` | Yes | Display name of project |
| `odoo_version` | Yes | Target Odoo version (14.0-18.0) |
| `project_version` | Yes | Current project version |
| `repo_name` | Yes | Repository name |
| `custom_folder` | Yes | Path to local addons |
| `external_folder` | Yes | Path to external addon repos |
| `pending_folder` | Yes | Path to pending merges |
| `marabunta_mig_file_rel_path` | No | Path to migration file |
| `cloud.*` | No | Cloud platform credentials |

## Odoo Version Support

Supported versions: 14.0, 15.0, 16.0, 17.0, 18.0

Choose based on:
- Customer requirements
- Community support timeline
- Module availability

Example:
```yaml
odoo_version: "16.0"  # Long-term support until August 2024
```

## Version Format

Project version follows Odoo release format: `ODOO_VERSION.MAJOR.MINOR.PATCH.BUILD`

Examples:
- `16.0.1.0.0` - First release for Odoo 16.0
- `16.0.1.1.0` - First fix for that release
- `17.0.2.0.0` - Major version bump for Odoo 17.0

## Version Bumping

Version bumping is handled by release tools:

```bash
# Automatic using bumpversion
otools-release bump major|minor|patch

# Manual via manifest edit
# Edit .odoo_tools/manifest.yml and project_version field
```

## Git Configuration

After initialization, pre-commit hooks are installed:

```bash
# Hooks automatically run on git commit
# Checks code style, linting, format compliance

# Manual run before committing
pre-commit run -a
```

## Database Configuration

Specify database settings in manifest:

```yaml
database:
  name: "my_project_db"
  host: "localhost"
  port: 5432
  user: "odoo"
  password: "secret"  # Use env vars in production!
```

Or use environment variables:
```bash
export DB_NAME=my_database
export DB_PASSWORD=secret
```

## Cloud Integration

For projects using Camptocamp's cloud platform:

```yaml
cloud:
  project_id: "camp-123456"
  database_name: "my_real_database"
  environment: "production"  # or staging, development
```

## Creating Test Projects

For testing purposes, create fake projects:

```python
# In tests
from tests.common import make_fake_project_root

@pytest.mark.project_setup(
    manifest=dict(odoo_version="16.0", project_version="16.0.1.0.0"),
    proj_version="16.0.1.0.0"
)
def test_with_fake_project(runner, project):
    # Fake project is created in isolated filesystem
    pass
```

See [tests/conftest.py](tests/conftest.py) and [tests/common.py](tests/common.py) for helpers.

## Project Initialization Workflow

1. **Create repository** with your Odoo project structure
2. **Run initialization**:
   ```bash
   otools-project init
   ```
3. **Update manifest.yml** with your project details
4. **Create addon directories**:
   ```bash
   mkdir -p addons external pending
   ```
5. **Add migration file** (if using Marabunta):
   ```bash
   mkdir -p migrations
   touch migrations/16.0.1.0.0.yml
   ```
6. **Install pre-commit hooks**:
   ```bash
   pre-commit run -a
   ```
7. **Test initialization**:
   ```bash
   otools-project show  # View current config
   ```

## Validating Configuration

Check if configuration is valid:

```bash
# Try to load configuration
python3 -c "from odoo_tools.utils.config import config; print(config.odoo_version)"

# Should print your Odoo version without errors
```

## Common Issues

| Issue | Solution |
|-------|----------|
| "manifest.yml not found" | Run `otools-project init` in project root |
| "Invalid Odoo version" | Ensure version matches 14.0, 15.0, 16.0, 17.0, or 18.0 |
| "custom_folder not found" | Ensure `addons/` directory exists (or update path) |
| "Config not reloading" | Call `config._reload()` after modifying files |

## Related Files

- [.odoo_tools/manifest.yml Example](templates/manifest.yml)
- [README.md Template](templates/README.md)
- [.pre-commit-config.yaml Template](templates/.pre-commit-config.yaml)

## Next Steps After Initialization

1. [Addon Management](../addon-management/SKILL.md) - Add and manage addon dependencies
2. [Project Development](../cli-development/SKILL.md) - Develop custom functionality
3. [Testing](../testing-quality/SKILL.md) - Test your addons
4. [Release Management](../release-management/SKILL.md) - Release your project

## Related Skills

- [Addon Management](../addon-management/SKILL.md) - Manage addon dependencies
- [Release Management](../release-management/SKILL.md) - Release versions
- [Testing & Quality](../testing-quality/SKILL.md) - Test your project
