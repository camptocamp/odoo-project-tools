---
name: pr-testing
description: Execute and review pull request validation workflows with otools-pr, including addon-targeted tests and result analysis. Use when validating PR changes locally before merge.
---

# Pull Request Testing Skill

## Purpose
Test pull request changes locally with otools-pr: run Odoo instances with PR branches, validate addon installations, and ensure quality before merging.

## Quick Reference

### Test PR Locally
```bash
otools-pr test --pr 123
```

### Test Specific Addon
```bash
otools-pr test --addon custom/addon_name --pr 123
```

### Show Test Results
```bash
otools-pr show --pr 123
```

### List Available Tests
```bash
otools-pr list
```

## PR Testing Workflow

Complete workflow for testing a pull request:

```bash
# 1. List available test configurations
otools-pr list

# 2. Start test for specific PR
otools-pr test --pr 123 --addon custom/addon_name

# 3. Monitor test progress
otools-pr show --pr 123

# 4. If test passes, prepare for merge
git pull origin feature/branch

# 5. If test fails, review logs
otools-pr show --pr 123 --logs

# 6. Once resolved, cleanup
otools-pr cleanup --pr 123
```

## Running Tests

### Simple PR Test

```bash
# Test PR 123
otools-pr test --pr 123

# This will:
# 1. Checkout PR branch
# 2. Create test database
# 3. Start Odoo instance
# 4. Install all addons
# 5. Run addon tests
# 6. Report results
```

### Test Specific Addon

```bash
# Test only custom addon
otools-pr test --addon custom/addon_name --pr 123

# Test multiple addons
otools-pr test \
  --addon custom/addon_name \
  --addon external/another_addon \
  --pr 123
```

### Test with Configuration

```bash
# Test with specific Odoo version
otools-pr test --pr 123 --version 16.0

# Test with database dump
otools-pr test --pr 123 --database prod_copy

# Test with custom settings
otools-pr test \
  --pr 123 \
  --timeout 600 \
  --skip-tests \
  --verbose
```

Options:
- `--pr PR_ID`: Pull request ID to test
- `--addon NAME`: Addon to test (can repeat)
- `--version VERSION`: Odoo version (default: from manifest)
- `--database DB`: Test database name
- `--timeout SECONDS`: Test timeout limit
- `--skip-tests`: Skip automated tests, just run instance
- `--verbose`: Detailed output

## Test Database Setup

Tests use separate database per PR:

```bash
# Created automatically
otools-pr test --pr 123  # Creates test_pr_123 database

# Or specify manually
otools-pr test --pr 123 --database custom_test_db
```

Database is cleaned up after test (unless `--keep-db` used):

```bash
# Keep database for inspection
otools-pr test --pr 123 --keep-db

# Later cleanup
otools-pr cleanup --pr 123
```

## Viewing Test Results

### Show Test Status

```bash
# View latest test
otools-pr show --pr 123

# Show detailed output
otools-pr show --pr 123 --verbose

# Show test logs
otools-pr show --pr 123 --logs

# Show test summary
otools-pr show --pr 123 --summary
```

### Test Pass/Fail Criteria

Tests pass if:
1. All addon dependencies resolve
2. Addon installs without errors
3. No database integrity violations
4. All unit tests (if configured) pass
5. No Python import errors

### Interpreting Test Output

```
Test PR #123: PASSED
  ✓ Addon dependencies resolved
  ✓ All addons installed
  ✓ 45 tests executed
  ✓ 0 failures
  ✓ 0 skipped

Database: test_pr_123
Duration: 2m 34s
```

## Manual Testing Steps

If automated tests insufficient:

```bash
# 1. Start test instance
otools-pr test --pr 123 --skip-tests

# 2. Instance starts at http://localhost:8069
# 3. Log in with admin credentials (or configured user)

# 4. In Odoo UI:
#    - Go to Apps
#    - Search for addon
#    - Install addon
#    - Test features manually

# 5. Run specific module tests
#    - Go to Settings > Modules (Developer mode)
#    - Select module with Tests
#    - Run Tests

# 6. Check logs
#    - Go to Settings > Logs
#    - Review error/warning messages

# 7. Stop instance when done (Ctrl-C)
```

## Integration with Pending Merges

Test pending merges alongside PR branches:

```bash
# Test PR with pending branches aggregated
otools-pr test \
  --pr 123 \
  --pending external/addon_name \
  --aggregate

# This tests PR + pending changes combined
```

## Addon-Specific Testing

### Test-Specific Addon Features

```bash
# Test addon with specific data
otools-pr test --pr 123 --addon custom/addon_name

# If addon has tests defined in __manifest__.py
# tests/test_models.py will execute
```

### External Dependencies

If addon requires external dependencies:

```python
# my_addon/__manifest__.py
{
    'name': 'My Addon',
    'external_dependencies': {
        'python': ['requests', 'lxml'],
        'bin': ['graphviz'],
    },
}
```

Ensure they're installed before testing:

```bash
# Install dependencies
pip install requests lxml
apt-get install graphviz

# Then test
otools-pr test --pr 123
```

## Performance Testing

For resource-intensive addons:

```bash
# Test with performance monitoring
otools-pr test --pr 123 --perf

# Shows:
# - Query count
# - Average response time
# - Memory usage
# - Database size growth
```

## Parallel Testing

Test multiple PRs simultaneously:

```bash
# Test several PRs
otools-pr test --pr 123
otools-pr test --pr 124
otools-pr test --pr 125

# Each uses separate database and port
# Results in all three running concurrently
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "PR not found" | Verify PR ID is correct |
| "Addon installation fails" | Check dependencies, review logs |
| "Database creation fails" | Verify PostgreSQL running |
| "Port already in use" | Wait for previous test, or use different port |
| "Test timeout" | Increase timeout with `--timeout 900` |

## Test Configuration Files

Tests can be configured in project:

```yaml
# .odoo_tools/test_config.yml
test_settings:
  default_timeout: 600
  packages_to_install:
    - requests
    - lxml
  environment:
    LOG_LEVEL: info

  pr_testing:
    always_skip_demo: true
    check_translations: false
```

## Related Documentation

See [docs/otools-pr.md](../docs/otools-pr.md) for detailed PR testing workflow.

## Related Skills

- [Addon Management](../addon-management/SKILL.md) - Managing addons being tested
- [Database Operations](../database-operations/SKILL.md) - Database setup/teardown
- [Testing & Quality](../testing-quality/SKILL.md) - General testing practices
