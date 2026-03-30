---
name: pending-merges-git
description: Track, add, aggregate, and remove pending pull request merges with otools-pending and git workflows. Use when coordinating temporary PR branches before upstream merges.
---

# Git & Pending Merges Skill

## Purpose
Manage pending merges and perform git aggregations on repositories using otools-pending. Handle pull requests, branch management, and repository coordination across multiple addon sources.

## Quick Reference

### Show All Pending Merges
```bash
otools-pending show
```

### Show Pending for Specific Repo
```bash
otools-pending show --repo custom/addon_name
```

### Add a Pending Merge
```bash
otools-pending add https://github.com/user/addon/pulls/123
```

### Aggregate Branches
```bash
otools-pending aggregate --repo custom/addon_name
```

### Remove a Pending Merge
```bash
otools-pending remove https://github.com/user/addon/pulls/123
```

## Command Overview

### Show: List Pull Requests

List all pending pull requests:

```bash
# All pending PRs
otools-pending show

# For specific repository
otools-pending show --repo external/addon_name

# Filter by state
otools-pending show --state draft
otools-pending show --state review
otools-pending show --state approved

# Purge closed/merged PRs
otools-pending show --purge-closed
otools-pending show --purge-merged
```

Options:
- `--repo REPO`: Filter to specific repository
- `--state {draft|review|approved}`: Filter by PR state
- `--purge-closed`: Remove closed PRs from tracking
- `--purge-merged`: Remove merged PRs from tracking

### Add: Add Pending Merge

Add a PR from GitHub:

```bash
# Basic
otools-pending add https://github.com/user/repo/pull/123

# With aggregation
otools-pending add https://github.com/user/repo/pull/123 --aggregate

# With patch
otools-pending add https://github.com/user/repo/pull/123 --patch path/to/patch.diff

# Push result to remote
otools-pending add https://github.com/user/repo/pull/123 --push-branch aggregated
```

Options:
- `--aggregate`: Run git aggregation immediately
- `--patch PATH`: Apply patch file to merge
- `--push-branch NAME`: Push aggregated result to remote branch
- `--force`: Overwrite existing pending merge

### Aggregate: Git Aggregation

Combine multiple branches into one:

```bash
# Aggregate branches for repository
otools-pending aggregate --repo custom/addon_name

# With push to remote
otools-pending aggregate --repo custom/addon_name --push-branch aggregated

# Dry run (preview without applying)
otools-pending aggregate --repo custom/addon_name --dry-run
```

Options:
- `--repo REPO`: Repository to aggregate
- `--push-branch BRANCH`: Push result to remote branch
- `--dry-run`: Preview changes without applying

### Remove: Remove Pending Merge

```bash
# Remove specific PR
otools-pending remove https://github.com/user/repo/pull/123

# With aggregation after removal
otools-pending remove https://github.com/user/repo/pull/123 --aggregate

# Remove all for repository
otools-pending remove --repo custom/addon_name --all
```

Options:
- `--aggregate`: Re-aggregate after removal
- `--all`: Remove all pending for repository

## Pending Merge Directory Structure

Pending merges are stored in `pending/` folder:

```
pending/
├── addon_name/
│   ├── main/                    # Main branch aggregation
│   │   ├── branch1/
│   │   │   └── ...
│   │   ├── branch2/
│   │   │   └── ...
│   │   └── files
│   ├── feature-branch/          # Alternative branch aggregation
│   │   └── ...
│   ├── .repo.yml               # Repo configuration
│   └── ...
└── another_addon/
    └── ...
```

## Git Aggregation Workflow

Git aggregation combines multiple feature branches:

```bash
# 1. Add PR for addon (creates pending merge)
otools-pending add https://github.com/user/addon/pull/123

# 2. View pending merge status
otools-pending show --repo external/addon_name

# 3. Aggregate branches (combine all pending)
otools-pending aggregate --repo external/addon_name

# 4. Review aggregated result
git -C pending/addon_name/main log --oneline

# 5. Push aggregated branch to origin
otools-pending aggregate --repo external/addon_name --push-branch test-aggregated

# 6. Test the aggregated result
# ... run tests ...

# 7. If tests pass, create PR for aggregated branch
# ... open PR on GitHub ...

# 8. Once merged, remove from pending
otools-pending remove --repo external/addon_name --all
```

## Pulling PR Branches

Before aggregating, ensure you have the PR branches:

```bash
# Fetch all remote branches
git fetch origin

# Or fetch specific branch
git fetch origin pull/123/head:feature-branch

# List remote branches
git branch -r
```

## Handling Merge Conflicts

If aggregation has conflicts:

```bash
# Check conflict status
git status

# Resolve conflicts manually
# Edit conflicting files

# Mark as resolved
git add conflicting_file.py

# Complete merge
git commit -m "Resolve merge conflict"
```

Or abort and retry:
```bash
# Abort aggregation
git merge --abort

# Re-aggregate with different branches
otools-pending aggregate --repo addon_name --dry-run
```

## Branch Naming Conventions

Follow consistent naming:

```bash
# Feature branches
feature/JIRA-123
feature/new-functionality

# Bugfix branches
bugfix/JIRA-456
bugfix/wrong-calculation

# Release branches
release/16.0.1.0.0

# Hotfix branches
hotfix/critical-bug

# Aggregation branches
aggregated/16.0
test/all-pending
```

## Integration with Addon Management

Pending merges work with addon workflows:

```bash
# 1. Add addon with pending branch
otools-addon add \
  --repo https://github.com/user/addon \
  --branch feature/fix-bug \
  external/addon

# 2. Creates pending merge automatically
otools-pending show --repo external/addon

# 3. Aggregate when ready to test
otools-pending aggregate --repo external/addon

# 4. Run tests
otools-ba run 16.0

# 5. Remove when merged to main
otools-pending remove --repo external/addon --all
```

## GitHub Integration Tips

### Linking PR to JIRA

Use PR description:

```markdown
Fixes JIRA-123

## Changes
- Implemented feature X
- Fixed bug Y

## Testing
- Unit tests added
- Manual testing: [steps]
```

### Reviewing PR Changes

```bash
# Show PR changes before aggregating
git log --oneline origin/feature-branch...main

# Show full diff
git diff main...origin/feature-branch

# Show with commit details
git log -p main..origin/feature-branch
```

### Auto-Linking Commits

Use commit messages:

```bash
git commit -m "Implement feature

JIRA-123 Description of what was done"
```

## Cleanup and Maintenance

Regular maintenance of pending merges:

```bash
# Purge merged PRs
otools-pending show --purge-merged

# Purge closed PRs
otools-pending show --purge-closed

# Clean up old branches
git -C pending/addon_name/main branch -D old-branch

# Reset pending folder
rm -rf pending/addon_name/*
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Pending folder not found" | Run from project root and ensure folder exists |
| "Merge conflict in aggregation" | Use `git merge --abort`, resolve, restart |
| "PR branch not found" | Run `git fetch origin` to sync remote branches |
| "Permission denied pushing" | Check GitHub auth token, SSH keys configured |
| "Aggregation creates unwanted commits" | Check branch ordering in .repo.yml |

## Related Skills

- [Addon Management](../addon-management/SKILL.md) - Adding addons with pending branches
- [PR Testing](../pr-testing/SKILL.md) - Testing pending changes with otools-pr
- [Testing & Quality](../testing-quality/SKILL.md) - Running tests on aggregated branches
