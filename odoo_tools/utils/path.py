# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from contextlib import contextmanager
from functools import cache
from pathlib import Path


@cache
def root_path():
    # The project root is the top of the git working tree. Cached because
    # build_path() calls this frequently and we must not spawn git every time.
    from .git import git_toplevel

    return git_toplevel()


def build_path(path):
    return root_path() / path


@contextmanager
def cd(path):
    """Temporarily change the current working directory.

    Beware: the working directory is process-global, so this is *not* safe to
    use in code that may run concurrently -- it would change the directory
    under the feet of the other threads, and with it what :func:`root_path`
    resolves to. Pass ``cwd=`` to the command being run instead.
    """
    prev = Path.cwd()
    os.chdir(Path(path).expanduser())
    try:
        yield
    finally:
        os.chdir(prev)


def is_odoo_module(path: Path) -> bool:
    """Check if a path is a valid Odoo module."""
    return path.is_dir() and (
        (path / "__manifest__.py").exists() or (path / "__openerp__.py").exists()
    )
