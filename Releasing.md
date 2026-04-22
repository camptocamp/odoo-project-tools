# how to release

The package version is derived automatically from the git tag by
[`hatch-vcs`](https://github.com/ofek/hatch-vcs), so there is no version
number to edit in any source file.

Run:

    export VERSION=x.y.z
    towncrier build --version=$VERSION
    git commit -m "Release $VERSION"
    git tag -as $VERSION
    # copy the content from HISTORY.rst into the tag annotation
    git push --tags && git push
    uv build

then create a release on https://github.com/camptocamp/odoo-project-tools/releases
and upload the artifacts from the [dist](dist/) directory to the release.

To verify the installed version at any time:

    otools-project --version
