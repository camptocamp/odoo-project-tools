# How to release

The package version is derived automatically from the git tag by
[`hatch-vcs`](https://github.com/ofek/hatch-vcs), so there is no version
number to edit in any source file.

Releases and tags are created directly from the GitHub UI:

1. Go to the [releases page](https://github.com/camptocamp/odoo-project-tools/releases)
   and click **Draft a new release**.
2. Create a new tag for the version you want to release (e.g. `x.y.z`).
3. Click **Generate release notes** to automatically populate the release
   notes from the merged pull requests since the previous release.
4. Review the notes and click **Publish release**.

## Automated build

Publishing a release triggers the
[`release` GitHub workflow](.github/workflows/release.yml), which automatically
builds the package with `uv build` and uploads the resulting artifacts to the
GitHub release. There is nothing to build or upload manually.
