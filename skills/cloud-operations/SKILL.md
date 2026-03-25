# Cloud Operations Skill

## Purpose
Interact with Camptocamp's cloud platform using otools-cloud: manage deployments, database dumps, environments, and cloud-hosted Odoo instances.

## Quick Reference

### Show Cloud Projects
```bash
otools-cloud show
```

### List Cloud Databases
```bash
otools-cloud db list
```

### Download Database Dump
```bash
otools-cloud db dump --project camp-123456 --database production_db
```

### Deploy to Cloud
```bash
otools-cloud deploy --environment staging
```

## Cloud Platform Configuration

Configure cloud access in project manifest:

```yaml
# .odoo_tools/manifest.yml
cloud:
  project_id: "camp-123456"
  database_name: "my_database"
  environment: "production"       # production, staging, development
  region: "eu"                    # eu, us, etc.
  credentials_file: "~/.cloud/credentials.json"
```

Or use environment variables:

```bash
export CLOUD_PROJECT_ID=camp-123456
export CLOUD_DATABASE=my_database
export CLOUD_ENVIRONMENT=production
export CLOUD_API_KEY=your_api_key
```

## Cloud Commands

### Show Project Info

```bash
# Show current project
otools-cloud show

# Show project details
otools-cloud show --project camp-123456 --verbose

# List all available projects
otools-cloud show --all-projects
```

### List Databases

```bash
# List all cloud databases
otools-cloud db list

# For specific project
otools-cloud db list --project camp-123456

# With sizes and metadata
otools-cloud db list --verbose
```

### Download Database Dump

```bash
# Download production database
otools-cloud db dump --database production_db

# Save to specific location
otools-cloud db dump \
  --database production_db \
  --output ./backups/prod_dump.sql.gz

# Download with timestamp
otools-cloud db dump \
  --database production_db \
  --output ./backups/prod_$(date +%Y%m%d).sql.gz
```

Options:
- `--database DB_NAME`: Database to dump
- `--output PATH`: Output file location
- `--format {sql|compressed|custom}`: Dump format
- `--include-data`: Include data (default: true)
- `--anonymize`: Anonymize sensitive data (PII)

### Restore Dump Locally

After downloading dump:

```bash
# Restore cloud dump to local database
otools-db restore \
  --name prod_local \
  --input ./backups/prod_dump.sql.gz

# Now use locally
otools-ba run 16.0 --database prod_local
```

### Deploy to Environment

Deploy current code to cloud:

```bash
# Deploy to staging
otools-cloud deploy --environment staging

# Deploy to production
otools-cloud deploy --environment production

# Dry run (preview changes)
otools-cloud deploy --environment staging --dry-run

# With custom branch
otools-cloud deploy \
  --environment staging \
  --branch feature/new-feature
```

Options:
- `--environment {development|staging|production}`: Target environment
- `--branch BRANCH`: Git branch to deploy
- `--skip-migrations`: Skip migration execution
- `--force`: Force deploy without confirmation
- `--dry-run`: Preview without applying

## Cloud Environment Management

### List Environments

```bash
# Show available environments
otools-cloud env list

# Show details
otools-cloud env show --environment production
```

### Environment Settings

```bash
# Check environment variables
otools-cloud env vars --environment staging

# Update environment variable
otools-cloud env set-var \
  --environment staging \
  --name LOG_LEVEL \
  --value debug

# Remove environment variable
otools-cloud env unset-var \
  --environment staging \
  --name TEMP_VAR
```

## Backup and Restore Workflow

Typical cloud backup workflow:

```bash
# 1. List available backups
otools-cloud backup list

# 2. Create on-demand backup
otools-cloud backup create --database production_db

# 3. Download backup locally
otools-cloud db dump \
  --database production_db \
  --output ./backups/backup-$(date +%s).sql.gz

# 4. Verify backup locally
otools-db restore --name backup_test --input ./backups/backup-*.sql.gz

# 5. Run tests with backup
otools-ba run 16.0 --database backup_test

# 6. Clean up
otools-db drop --name backup_test --force
```

## Development Setup from Production

Copy production for development:

```bash
# 1. Download production dump
otools-cloud db dump --database production_db --output prod.sql.gz

# 2. Create local dev database
otools-db create --name dev_from_prod

# 3. Restore production data
otools-db restore \
  --name dev_from_prod \
  --input prod.sql.gz \
  --force

# 4. Optional: anonymize sensitive data
# ... run anonymization script ...

# 5. Use for development
otools-ba run 16.0 --database dev_from_prod
```

## Multi-Environment Deployment

Manage code across environments:

```bash
# Deploy sequence
# 1. Test in development
otools-cloud deploy --environment development

# 2. If OK, deploy to staging
otools-cloud deploy --environment staging

# 3. If staging OK, deploy to production
otools-cloud deploy --environment production

# Rollback if needed
otools-cloud rollback --environment production --to-deployment 123
```

## Environment Promotion

Promote database between environments:

```bash
# Copy staging database to development
otools-cloud db copy \
  --source staging \
  --destination development \
  --force

# This creates a backup, then restores to target
```

## Logs and Monitoring

Access cloud logs:

```bash
# Show recent logs
otools-cloud logs --environment production --lines 100

# Stream live logs
otools-cloud logs --environment production --follow

# Filter logs
otools-cloud logs \
  --environment production \
  --level ERROR \
  --module purchase
```

Options:
- `--lines NUMBER`: Show last N lines
- `--follow`: Stream logs in real-time
- `--level {DEBUG|INFO|WARNING|ERROR|CRITICAL}`: Filter by level
- `--module NAME`: Filter by module
- `--since TIME`: Logs since timestamp

## Cloud User Management

Manage cloud project users:

```bash
# List project members
otools-cloud members list

# Add user
otools-cloud members add \
  --email user@camptocamp.com \
  --role developer

# Remove user
otools-cloud members remove --email user@camptocamp.com

# Roles: viewer, developer, operator, admin
```

## Authentication

Set up cloud authentication:

```bash
# Login to cloud platform
otools-cloud auth login

# This creates ~/.cloud/credentials.json

# Verify authentication
otools-cloud auth verify

# Logout
otools-cloud auth logout
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Authentication failed" | Run `otools-cloud auth login` |
| "Project not found" | Verify project ID in manifest.yml |
| "Database dump fails" | Check internet connection, disk space |
| "Deploy timeout" | Increase timeout, or retry deploy |
| "Environment not accessible" | Verify permissions in cloud console |

## Cloud Configuration Best Practices

1. **Never commit credentials** to git
2. **Use environment variables** for sensitive data
3. **Separate staging/production** for critical changes
4. **Regular backups** before deployments
5. **Test locally first** before cloud deployment
6. **Use read-only tokens** for CI/CD pipelines

## Related Skills

- [Database Operations](../database-operations/SKILL.md) - Local database management
- [Release Management](../release-management/SKILL.md) - Version releases to cloud
- [Testing & Quality](../testing-quality/SKILL.md) - Pre-deployment validation
