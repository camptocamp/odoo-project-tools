# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from manifestoo.addons_selection import AddonsSelection
from manifestoo.commands.list import list_command
from manifestoo.commands.list_codepends import list_codepends_command
from manifestoo.commands.list_depends import list_depends_command
from manifestoo_core.addons_set import AddonsSet

from . import ui
from .config import config
from .path import build_path


def get_addons_dirs() -> list[Path]:
    """Return all the directories where the project's addons are located."""
    addons_dirs = []
    # local-src: addons are direct children
    addons_dirs.append(build_path(config.local_src_rel_path))
    # external-src: each subdirectory is a repo containing addons
    ext_src = build_path(config.ext_src_rel_path)
    if ext_src.is_dir():
        for repo_dir in sorted(ext_src.iterdir()):
            if repo_dir.is_dir():
                addons_dirs.append(repo_dir)
    # Odoo community and base addons
    odoo_src = build_path(config.odoo_src_rel_path)
    addons_dirs.append(odoo_src / "addons")
    addons_dirs.append(odoo_src / "odoo" / "addons")
    return addons_dirs


def get_addons_set() -> AddonsSet:
    """Return the set of all addons found in the project's addons directories."""
    addons_set = AddonsSet()
    addons_set.add_from_addons_dirs(get_addons_dirs())
    return addons_set


def get_local_addons_selection() -> AddonsSelection:
    """Return a selection holding the project's local addons."""
    selection = AddonsSelection()
    selection.add_addons_dirs([build_path(config.local_src_rel_path)])
    return selection


def get_addons_selection(addon_names: Iterable[str]) -> AddonsSelection:
    """Return a selection holding the given addon names.

    Each name may itself be a comma separated list of addon names.
    """
    selection = AddonsSelection()
    for addon_name in addon_names:
        selection.add_addon_names(addon_name)
    return selection


def list_addons(
    selection: AddonsSelection,
    addons_set: AddonsSet,
) -> list[str]:
    """Return the names of the selected addons."""
    return list(list_command(selection, addons_set))


def list_depends(
    selection: AddonsSelection,
    addons_set: AddonsSet,
    transitive: bool = False,
    include_selected: bool = False,
    ignore_missing: bool = False,
) -> tuple[list[str], list[str]]:
    """Return the dependencies of the selected addons.

    Returns a tuple ``(addon_names, missing_addon_names)`` where the second
    item holds the addons that were not found in the addons directories.
    Missing addons raise an error, unless ``ignore_missing`` is set.
    """
    addon_names, missing = list_depends_command(
        selection,
        addons_set,
        transitive=transitive,
        include_selected=include_selected,
    )
    if missing and not ignore_missing:
        ui.exit_msg(f"Addon(s) not found: {', '.join(sorted(missing))}")
    return list(addon_names), sorted(missing)


def list_codepends(
    selection: AddonsSelection,
    addons_set: AddonsSet,
    transitive: bool = True,
    include_selected: bool = True,
    ignore_missing: bool = False,
) -> tuple[list[str], list[str]]:
    """Return the co-dependencies of the selected addons.

    Co-dependencies are the addons that depend on the selected addons.

    Returns a tuple ``(addon_names, missing_addon_names)`` where the second
    item holds the selected addons that were not found in the addons
    directories. Missing addons raise an error, unless ``ignore_missing``
    is set.
    """
    missing = sorted(selection - addons_set.keys())
    if missing and not ignore_missing:
        ui.exit_msg(f"Addon(s) not found: {', '.join(missing)}")
    addon_names = list(
        list_codepends_command(
            selection,
            addons_set,
            transitive=transitive,
            include_selected=include_selected,
        )
    )
    return addon_names, missing
