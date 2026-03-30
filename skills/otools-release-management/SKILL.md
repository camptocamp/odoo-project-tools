---
name: otools-release-management
description: Drive package release workflows for odoo-project-tools, including changelog generation, version bumping, tagging, building, and publishing. Use when preparing or executing a software release.
---

# Release Management Skill

## Purpose
Manage the release process for odoo-project-tools: bump version numbers, update changelog, build distributions, and deploy releases following Git and GitHub best practices.

## Quick Reference

### Quick Release Workflow
```bash
export VERSION=1.2.3
uv run towncrier build --version=$VERSION
git commit -m "prepare $VERSION"
git tag -as $VERSION  # -s to sign, omit -s if unsigned
# Copy HISTORY.rst content into tag annotation
git push --tags && git push
python3 -m build
```

Then upload wheel from `dist/` to GitHub release.

## Release Manager Checklist

### 1. Check Changelog
```bash
# Review changelog fragments in changes.d/
ls -la changes.d/
git diff HEAD -- changes.d/
```

### 2. Bump Version
```bash
# Option A: Auto-detect version bump from changelog
uv run towncrier build --version=X.Y.Z

# Option B: Use bumpversion for specific type
uv run bumpversion major  # or minor, patch
```

### 3. Update Migration File (if applicable)
If the project has Marabunta migrations:
```bash
# Edit the migration file referenced in project config
# Ensure it's updated with changes for this release
cat .odoo_tools/manifest.yml | grep marabunta_mig_file_rel_path
```

### 4. Build Distribution
```bash
python3 -m build
ls -la dist/
```

### 5. Create Git Tag
```bash
git tag -as v1.2.3  # -s signs the tag with GPG
# Paste HISTORY.rst content as tag annotation
git show v1.2.3
```

### 6. Push to GitHub
```bash
git push origin main --tags
```

### 7. Create GitHub Release
1. Go to https://github.com/camptocamp/odoo-project-tools/releases
2. Create new release from tag
3. Upload wheel from `dist/odoo_tools-X.Y.Z-py3-none-any.whl`
4. Copy release notes from HISTORY.rst

## Version Format

Version follows semantic versioning: `MAJOR.MINOR.PATCH[-PRERELEASE]`

Examples: `1.0.0`, `1.2.3`, `2.0.0-alpha.1`

## Changelog Management

### Adding Changelog Fragments

Before release, create changelog fragments in `changes.d/`:

```bash
# Command: fragment [ISSUE_ID].{feat|fix|doc|build}.rst
# Filename format: [ISSUE_ID|COMMIT_SHORT].{feat|fix|doc|build}.rst
# Example: +ab12c34.feat.rst
```

File content example:
```rst
Fixed bug in addon requirement parsing
```

### Fragment Types

| Type | Purpose |
|------|---------|
| `.feat.rst` | New feature |
| `.fix.rst` | Bug fix |
| `.doc.rst` | Documentation improvement |
| `.build.rst` | Build/CI/tooling change |

### View Consolidated Changelog

After running `towncrier build`:
```bash
head -50 HISTORY.rst  # See compiled changelog
```

## Configuration Files

- **pyproject.toml**: Contains `[tool.towncrier]` config, version number
- **VERSION** or version in pyproject: Reference in bump tools
- **.bumpversion.cfg**: Bump2version configuration for version bumping

## Key Files Modified During Release

1. `HISTORY.rst` - Consolidated changelog
2. `pyproject.toml` - Version number
3. `odoo_tools/__init__.py` - Package version variable (if used)
4. Marabunta migration file (if applicable)

All changes must be committed before tagging.

## Pre-Release Checks

Before running release:

```bash
# 1. Check you're on release branch (usually main)
git status
git log --oneline -5

# 2. Verify no uncommitted changes
git diff --stat

# 3. Review upcoming changelog
ls changes.d/ | head -10

# 4. Run full test suite
uv run pytest --verbose

# 5. Run quality checks
pre-commit run -a
```

## Release Artifacts

| File | Purpose |
|------|---------|
| `odoo_tools-X.Y.Z-py3-none-any.whl` | Installable wheel (main artifact) |
| `odoo_tools-X.Y.Z.tar.gz` | Source distribution |
| `pyproject.toml` | Updated with new version |

## Post-Release

After GitHub release is published:

1. **Verify installation works**:
   ```bash
   pip install --upgrade odoo-tools
   otools-project --version
   ```

2. **Announce release** on team channels

3. **Archive release notes** for future reference

4. **Plan next release** based on pending features

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Version not updated in X file" | Edit file manually, re-run bumpversion check |
| "Tag already exists" | Delete with `git tag -d v1.2.3`, re-tag with correct version |
| "HISTORY.rst not updated" | Run `towncrier build --version=X.Y.Z` before commit |
| "Build wheel fails" | Run `python3 -m build --verbose`, check distutils config |

## Related Skills

- [Development Environment Setup](../otools-dev-environment-setup/SKILL.md) - Building and dependencies
- [Testing & Quality Checks](../testing-quality/SKILL.md) - Pre-release validation
- [Git & Pending Merges](../otools-pending-merges-git/SKILL.md) - Managing branches before release
