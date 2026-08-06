---
name: otools-addon-management
description: Add, require, and update Odoo addons in project workspaces, including external repositories and pending branches. Use when the task involves addon dependency management or addon setup/testing workflows.
---

# Addon Management Skill

## Purpose
Add, manage, and update addon dependencies in Odoo projects using otools-addon. Handle addon requirements, pending compatibility, and testing addon changes.

## Quick Reference

### List Addons
```bash
otools-addon list
```

### Add an Addon
```bash
otools-addon add --repo github-url --branch main custom/addon_name
```

### Add with Pending
```bash
otools-addon add --repo https://github.com/org/addon --branch feature/new-feature \
  --pending /path/to/pending/addon
```

### Update Addon in Pending
```bash
otools-addon add-pending custom/addon_name
```

### Show Addon Details
```bash
otools-addon list --addon custom/addon_name
```

## Command Overview

### List: Display Project Addons
```bash
# List all addons in current project
otools-addon list

# List specific addon
otools-addon list --addon custom/addon_name

# Verbose output with paths
otools-addon list -v
```

### Add: Add New Addon to Project

```bash
otools-addon add \
  --repo https://github.com/OCA/account_invoicing \
  --branch 16.0 \
  external/account_invoicing
```

Options:
- `--repo URL`: GitHub URL of addon repository
- `--branch BRANCH`: Branch to checkout (default: main)
- `--pending PATH`: Path in pending/ if needed for testing
- `--force`: Overwrite existing addon

### Add-Pending: Update Addon with Pending Branch

Add a pending merge to an existing addon:

```bash
otools-addon add-pending custom/addon_name
```

This:
1. Creates a pending merge branch
2. Aggregates changes
3. Updates addon manifest

### Require: Add to Requirements

Add addon to project requirements file:

```bash
otools-addon require --addon account_invoicing --version 16.0
```

## Addon Directory Structure

Addons are organized in folders:

```
my-project/
├── addons/                          # Local/custom addons
│   ├── my_addon/
│   │   ├── __manifest__.py
│   │   ├── models/
│   │   ├── views/
│   │   └── ...
│   ├── another_addon/
│   └── ...
├── external/                        # External addons from other repos
│   ├── account_invoicing/           # From OCA or other source
│   ├── sale_management/
│   └── ...
└── pending/                         # Pending merge branches
    ├── addon_name/
    │   ├── main/                    # Main branch
    │   │   └── ...
    │   └── feature/new-feature/     # Feature branch
    │       └── ...
    └── ...
```

## Adding an Addon from OCA

OCA (Odoo Community Association) provides many addons:

```bash
# Add account invoicing from OCA
otools-addon add \
  --repo https://github.com/OCA/account-invoicing \
  --branch 16.0 \
  external/account_invoicing

# Add sale addons from OCA
otools-addon add \
  --repo https://github.com/OCA/sale-workflow \
  --branch 16.0 \
  external/sale_workflow
```

## Managing Addon Dependencies

### Check Addon Requirements

View dependencies in addon manifest:

```python
# my-project/addons/my_addon/__manifest__.py
{
    'name': 'My Addon',
    'version': '16.0.1.0.0',
    'depends': [
        'base',
        'sale',
        'account',
        'stock',
    ],
    'external_dependencies': {
        'python': ['requests', 'lxml'],
        'bin': ['wkhtmltopdf'],
    },
}
```

### Resolve Missing Dependencies

If addon requires other addons:

```bash
# Check which addons are needed
otools-addon list --addon my_addon -v

# Add missing dependencies
otools-addon add --repo {repo_url} --branch {branch} external/missing_addon
```

## Testing Addons with Pending

When testing changes from a pending merge:

```bash
# Add addon with pending changes
otools-addon add \
  --repo https://github.com/contributor/addon \
  --branch feature/fix-bug \
  --pending external/addon

# This merges the pending branch with main before testing
```

## Addon Validation

Before committing addon changes:

```bash
# Check manifest syntax
python3 -m py_compile addons/my_addon/__manifest__.py

# Verify addon loads in Odoo
# (requires running Odoo instance with test database)
otools-ba run 16.0  # Run test instance
# Then test addon installation in Odoo UI
```

## Common Addon Tasks

### Cloning an Addon Repository

```bash
# Clone full repo to external/
git clone https://github.com/OCA/account-invoicing.git \
  -b 16.0 \
  external/account_invoicing

# Or use otools-addon
otools-addon add \
  --repo https://github.com/OCA/account-invoicing \
  --branch 16.0 \
  external/account_invoicing
```

### Creating Custom Addon Template

```bash
# Scaffold new addon with cookiecutter
cookiecutter gh:ocsistemas/cookiecutter-odoo-addon \
  --no-input \
  addon_name=my_addon \
  addon_directory=addons

# Or copy from template
cp -r addons/addon_template addons/my_addon
```

### Removing Addon

```bash
# Remove from project
rm -rf external/unwanted_addon

# Update requirements
otools-addon require --remove unwanted_addon
```

## Addon Version Management

Follow Odoo versioning for addons:

```python
# __manifest__.py
{
    'name': 'My Addon',
    'version': '16.0.1.0.0',  # Odoo.Major.Minor.Patch.Build
    'depends': ['base'],
    'installable': True,
}
```

Bump version on release:

```bash
otools-addon update-version --addon my_addon --version 16.0.1.1.0
```

## Git Workflow with Addons

### Adding Addon to Git

```bash
# Add new addon directory
git add addons/my_addon

# Add external addon
git add external/new_addon

# Commit with message
git commit -m "Add addon: my_addon for feature X"

# Push to origin
git push origin feature/add-addon
```

### Ignore External Addons

Add to `.gitignore`:

```gitignore
# External addons (managed separately)
external/*
!external/.gitkeep

# Pending merges
pending/*
!pending/.gitkeep
```

## Integration with Testing

Test addons before release:

```bash
# Run addon tests
otools-ba run 16.0

# In Odoo UI, install addon and verify functionality

# Or use automated tests
otools-pr test --addon my_addon
```

See [PR Testing](../otools-pr-testing/SKILL.md) for detailed testing workflow.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Addon not found" | Verify folder exists in `addons/` or `external/` |
| "Manifest syntax error" | Run `python -m py_compile` on manifest file |
| "Missing dependencies" | Use `otools-addon add` to install required addons |
| "Version mismatch" | Ensure addon Odoo version matches project version |
| "Git merge conflict" | Use `git merge --abort` and retry with specific branch |

## Related Skills

- [Project Setup](../otools-project-setup-initialization/SKILL.md) - Initialize project
- [Testing & Quality](../testing-quality/SKILL.md) - Test addon changes
- [PR Testing](../otools-pr-testing/SKILL.md) - Test PR changes with otools-pr
- [Git & Pending Merges](../otools-pending-merges-git/SKILL.md) - Manage pending merges
