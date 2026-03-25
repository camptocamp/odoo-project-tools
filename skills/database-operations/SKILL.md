# Database Operations Skill

## Purpose
Manage local Odoo databases using otools-db: create, drop, backup, restore, and manage database configuration for development and testing.

## Quick Reference

### List Local Databases
```bash
otools-db list
```

### Create New Database
```bash
otools-db create --name my_test_db
```

### Backup Database
```bash
otools-db backup --name my_test_db --output backup.sql
```

### Restore Database
```bash
otools-db restore --name my_test_db --input backup.sql
```

### Drop Database
```bash
otools-db drop --name my_test_db --force
```

## Database Configuration

Set database credentials in project config:

```yaml
# .odoo_tools/manifest.yml
database:
  name: "my_project_db"
  host: "localhost"
  port: 5432
  user: "odoo"
  password: "secret"
```

Or use environment variables:
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=odoo
export DB_PASSWORD=secret
```

## Database Operations

### Create Database

```bash
# Create with default settings
otools-db create --name test_db_001

# Create with options
otools-db create \
  --name test_db_001 \
  --host localhost \
  --port 5432 \
  --user odoo

# With template (e.g., copy from existing)
otools-db create --name new_db --template existing_db
```

Options:
- `--name NAME`: Database name (required)
- `--host HOST`: PostgreSQL host (default: localhost)
- `--port PORT`: PostgreSQL port (default: 5432)
- `--user USER`: Database user (default: odoo)
- `--template DB`: Use existing DB as template
- `--encoding`: Character encoding (default: UTF-8)

### List All Databases

```bash
# List all
otools-db list

# Verbose with details
otools-db list -v

# Show size
otools-db list --size
```

### Backup Database

```bash
# Simple backup
otools-db backup --name my_db --output backup.sql

# Compressed backup
otools-db backup --name my_db --output backup.sql.gz --compress

# Full backup with options
otools-db backup \
  --name my_db \
  --output /tmp/my_db_backup \
  --compress \
  --verbose
```

Options:
- `--name NAME`: Database to backup
- `--output PATH`: Output file path
- `--compress`: Compress output (gzip)
- `--format {plain|custom|directory}`: Backup format
- `--verbose`: Show detailed output

### Restore Database

```bash
# Restore from backup
otools-db restore --name restored_db --input backup.sql

# Restore to existing DB (drop first)
otools-db restore --name restored_db --input backup.sql --force

# From compressed backup
outils-db restore --name restored_db --input backup.sql.gz
```

Options:
- `--name NAME`: Target database name
- `--input PATH`: Input backup file
- `--force`: Drop existing database first
- `--verbose`: Show detailed output

### Drop Database

```bash
# Drop database (with confirmation)
otools-db drop --name old_db

# Drop without confirmation
otools-db drop --name old_db --force

# Drop multiple
otools-db drop --pattern "test_*" --force
```

Options:
- `--name NAME`: Database to drop
- `--pattern PATTERN`: Drop databases matching pattern
- `--force`: Skip confirmation prompt

## Testing Database Workflow

Typical testing setup:

```bash
# 1. Create test database
otools-db create --name test_db_001

# 2. Restore from production backup (if available)
# First obtain production dump: vendor provides via cloud console
otools-db restore --name test_db_001 --input prod_backup.sql

# 3. Run tests
otools-ba run 16.0 --database test_db_001

# 4. After testing, clean up
otools-db drop --name test_db_001 --force
```

## Backup and Restore Strategy

### Regular Backups

```bash
# Backup daily
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
otools-db backup \
  --name production_db \
  --output backups/prod_db_$TIMESTAMP.sql.gz \
  --compress
```

### Restore to Test

```bash
# Create test copy for quality assurance
otools-db restore \
  --name test_qa \
  --input backups/prod_db_latest.sql.gz

# Test changes without affecting production
# Use test_qa database in development
```

### Database Cloning

```bash
# Clone using template
otools-db create --name cloned_db --template source_db

# Or backup/restore
otools-db backup --name source_db --output clone.sql
otools-db restore --name cloned_db --input clone.sql
```

## PostgreSQL Direct Access

If direct PostgreSQL access is needed:

```bash
# Connect to database
psql -h localhost -U odoo -d my_db

# Or use environment variables
export PGHOST=localhost
export PGUSER=odoo
export PGDATABASE=my_db
export PGPASSWORD=secret
psql

# Common PostgreSQL commands
\l                          # List databases
\d                          # List tables
\du                        # List users
SELECT datname FROM pg_database;  # Query database list
```

## Data Anonymization

For production data in test environment:

```bash
# Create test database from production
otools-db restore --name test_anon --input prod_backup.sql

# Connect and anonymize (if automated scripts available)
psql -d test_anon < anonymize.sql

# Or manually update sensitive data
psql -d test_anon -c "UPDATE res_partner SET email = 'test@example.com';"
```

## Cloud Database Integration

If using Camptocamp cloud platform:

```yaml
# .odoo_tools/manifest.yml
cloud:
  project_id: "camp-123456"
  database_name: "production_db"
```

Backup from cloud:

```bash
# Download production dump from cloud console
# Then restore locally
otools-db restore --name prod_copy --input cloud_backup.sql.gz
```

## Docker Database Setup

If running Odoo in Docker:

```bash
# PostgreSQL container
docker run --name odoo_postgres \
  -e POSTGRES_PASSWORD=secret \
  -d postgres:14

# Connect to container database
PGPASSWORD=secret psql -h localhost -U postgres -d postgres

# Or use with otools-db
export DB_HOST=localhost
export PGPASSWORD=secret
otools-db list
```

## Performance Optimization

### Index Management

```bash
# Connect and analyze performance
psql -d my_db

# Create indexes for slow queries
CREATE INDEX idx_sale_order_state ON sale_order(state);

# Analyze query performance
EXPLAIN ANALYZE SELECT * FROM sale_order WHERE state='done';
```

### Autovacuum Maintenance

Databases should autovacuum regularly:

```bash
# Check autovacuum status
psql -d my_db -c "SHOW autovacuum;"

# Manual vacuum if needed
VACUUM my_db;
ANALYZE my_db;
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection refused" | Ensure PostgreSQL is running, check hostname/port |
| "Database does not exist" | Create with `otools-db create` |
| "Permission denied" | Verify user has DB creation privileges |
| "Restore fails" | Check backup file format, try with `--force` |
| "Out of space" | Drop unused databases, compress old backups |

## Related Skills

- [Database Testing with otools-ba](../functional-testing/SKILL.md) - Run Odoo instances
- [PR Testing](../pr-testing/SKILL.md) - Test with databases
