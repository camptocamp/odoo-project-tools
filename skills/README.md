# Odoo Project Tools Skills Index

This directory contains reusable skills for agents working with the `odoo-project-tools` repository. These skills document best practices, common workflows, and detailed command references for all major tool areas.

## Skills Overview

### 🚀 Getting Started

**[Development Environment Setup](otools-dev-environment-setup/SKILL.md)**
- Configure development environment with uv
- Install dependencies and optional extras
- Verify Python 3.10+ requirements
- Understand code style and Ruff configuration
- Troubleshoot common setup issues

### 🏗️ Project & Architecture

**[Project Setup & Initialization](otools-project-setup-initialization/SKILL.md)**
- Initialize new Odoo projects with `otools-project init`
- Configure `.odoo_tools/manifest.yml`
- Understand project structure and folder organization
- Set up Odoo version targeting and versioning
- Validate project configuration

### 📦 Working with Code

**[Addon Management](otools-addon-management/SKILL.md)**
- Add and manage addon dependencies
- Use `otools-addon list`, `add`, `require`
- Handle external addons from OCA and others
- Work with addon manifests and dependencies
- Manage pending addon branches

**[Git & Pending Merges](otools-pending-merges-git/SKILL.md)**
- Manage pending pull requests with `otools-pending`
- Use git aggregation to combine branches
- Show, add, remove, and aggregate pending merges
- Handle merge conflicts
- Integrate pending merges with addon workflows

### 🧪 Quality & Testing

**[Pull Request Testing](otools-pr-testing/SKILL.md)**
- Test PRs locally with `otools-pr test`
- Run Odoo instances with PR branches
- Validate addon installations
- Test specific addons and configurations
- Troubleshoot test failures

### 💾 Data & Deployment

**[Database Operations](otools-database-operations/SKILL.md)**
- Manage local databases with `otools-db`
- Create, backup, restore, and drop databases
- Configure database credentials
- Backup/restore workflows
- PostgreSQL direct access and optimization

**[Cloud Operations](otools-cloud-operations/SKILL.md)**
- Interact with Camptocamp cloud platform
- Download production dumps
- Deploy to environments (dev, staging, production)
- Manage cloud projects and databases
- Environment promotion and rollback

**[Release Management](otools-release-management/SKILL.md)**
- Manage releases with `otools-release`
- Bump versions automatically
- Generate changelogs with Towncrier
- Build distributions with Python build tools
- Upload releases to GitHub

## Skill Dependency Graph

```
otools-dev-environment-setup
├── otools-pr-testing
├── otools-release-management
└── otools-project-setup-initialization
    ├── otools-addon-management
    │   └── otools-pending-merges-git
    └── otools-database-operations
        └── otools-cloud-operations
```

## Quick Command Reference

### Project Initialization
```bash
# One-time setup
uv sync --dev --all-extras           # Install dependencies
otools-project init                   # Initialize project
pre-commit run -a                    # Validate setup
```

### Development Workflow
```bash
otools-addon add --repo {url} {path}  # Add addon
otools-pending show                   # Show pending PRs
otools-pending aggregate --repo {name} # Combine branches
uv run pytest tests/ -q              # Run tests
```

### Testing & QA
```bash
otools-pr test --pr 123                          # Test PR
otools-db create --name test_db                  # Create test DB
otools-ba run 16.0 --database test_db           # Run Odoo
```

### Release & Deploy
```bash
otools-release bump minor             # Bump version
python3 -m build                     # Build distribution
otools-cloud deploy --environment staging  # Deploy to cloud
```

## Skills by Role

### Software Developer
1. [Development Environment Setup](otools-dev-environment-setup/SKILL.md)
2. [Addon Management](otools-addon-management/SKILL.md)

### DevOps / Release Manager
1. [Release Management](otools-release-management/SKILL.md)
2. [Cloud Operations](otools-cloud-operations/SKILL.md)
3. [Database Operations](otools-database-operations/SKILL.md)
4. [Git & Pending Merges](otools-pending-merges-git/SKILL.md)

### QA Engineer
1. [Pull Request Testing](otools-pr-testing/SKILL.md)
2. [Database Operations](otools-database-operations/SKILL.md)
3. [Addon Management](otools-addon-management/SKILL.md)

### Project Manager / BA
- See [otools-ba documentation](../docs/otools-ba.md) for functional/non-technical workflows

## Key Concepts

### Code Organization
- **CLI Layer** (`odoo_tools/cli/`): Thin Click command orchestration
- **Utilities** (`odoo_tools/utils/`): Reusable business logic
- **Tests** (`tests/`): pytest-based test suite with Click runner fixtures
- **Tasks** (`odoo_tools/tasks/`): Legacy invoke tasks (deprecated for new work)

### Quality Standards
- **Line length**: 88 characters (Ruff enforced)
- **Python version**: 3.10+ (Ruff enforced)
- **Imports**: Prefer `pathlib` over `os.path`
- **Headers**: AGPL license required in Python files
- **Coverage**: 80%+ for new features, 100% for fixes

### Project Configuration
- **Manifest**: `.odoo_tools/manifest.yml` contains project metadata
- **Version format**: `ODOO_VERSION.MAJOR.MINOR.PATCH.BUILD`
- **Supported Odoo versions**: 14.0, 15.0, 16.0, 17.0, 18.0

## Common Workflows

### Adding a Feature
1. Create CLI command in `odoo_tools/cli/`
2. Implement utility functions in `odoo_tools/utils/`
3. Write tests with `pytest`
4. Run quality checks: `pre-commit run -a`
5. Create PR and test with `otools-pr test --pr {id}`
6. Merge and release (see [Release Management](otools-release-management/SKILL.md))

### Testing an Addon Change
1. Add addon with pending branch (see [Addon Management](otools-addon-management/SKILL.md))
2. Aggregate pending merges (see [Git & Pending Merges](otools-pending-merges-git/SKILL.md))
3. Test with `otools-pr test --addon {name}`
4. Review test results and logs
5. Merge pending changes to main

### Deploying to Production
1. Prepare release (see [Release Management](otools-release-management/SKILL.md))
2. Test in staging: `otools-cloud deploy --environment staging`
3. Verify in staging environment
4. Deploy to production: `otools-cloud deploy --environment production`
5. Monitor logs and rollback if needed

## Documentation References

- **Main README**: [README.md](../README.md)
- **Functional Workflow (BA)**: [docs/otools-ba.md](../docs/otools-ba.md)
- **PR Testing Workflow**: [docs/otools-pr.md](../docs/otools-pr.md)
- **Release Process**: [Releasing.md](../Releasing.md)
- **Project Guidelines**: [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Contributing New Skills

To add a new skill:

1. Create new directory: `skills/skill-name/`
2. Create `SKILL.md` with:
   - **Purpose**: What the skill covers
   - **Quick Reference**: Common commands
   - **Detailed Sections**: Organized by topic
   - **Examples**: Real-world usage
   - **Troubleshooting**: Common issues
   - **Related Skills**: Cross-references
3. Add to this index with brief description

## Support

For issues or improvements to skills:
- File issues on [GitHub](https://github.com/camptocamp/odoo-project-tools/issues)
- Update skills based on feedback and new features
- Keep examples current with latest tool versions

---

**Last Updated:** March 2026
**Tool Version**: odoo-project-tools (latest from main branch)
**Python**: 3.10+
