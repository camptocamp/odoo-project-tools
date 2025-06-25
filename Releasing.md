# how to release

Run

    export VERSION=x.y.z
    towncrier build --version=$VERSION
    git commit -m "prepare "$VERSION
    git tag -as $VERSION
    # copy the content from HISTORY.rst
    git push --tags && git push
    python3 -m build

Then [create a release](https://github.com/camptocamp/odoo-project-tools/releases)
and upload the wheel you will find in the [dist](dist/) directory to the release.
