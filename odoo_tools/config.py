# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import annotations

import os
from os import PathLike
from pathlib import Path
from textwrap import indent
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from .exceptions import ProjectConfigException
from .utils.misc import parse_ini_cfg
from .utils.path import build_path

# TODO: use this as marker file
PROJ_CFG_FILE = os.getenv("PROJ_CFG_FILE", ".proj.cfg")


def format_pydantic_validation_error(e: ValidationError) -> str:
    """Format a Pydantic validation error."""
    messages = []
    for error in e.errors():
        fname = error["loc"][0]
        message = f"- '{fname}': {error['msg']}"
        field = ProjectConfig.model_fields.get(fname)
        if field and field.description:
            message += f"\n\n{indent(field.description, ' ' * 4)}"
        messages.append(message)
    return "\n\n".join(messages)


def validate_config(config: dict[str, Any]) -> ProjectConfig:
    """Validates the configuration."""
    try:
        return ProjectConfig(**config)
    except ValidationError as e:
        raise ProjectConfigException(
            "The configuration is malformed.\n\n"
            f"{format_pydantic_validation_error(e)}"
        ) from None


def load_config(config_path: PathLike = PROJ_CFG_FILE) -> ProjectConfig:
    """Loads the configuration file."""
    try:
        with open(build_path(config_path, from_root=True)) as f:
            config = dict(parse_ini_cfg(f.read(), "conf")["conf"])
    except FileNotFoundError as e:
        raise ProjectConfigException(e) from e
    try:
        return validate_config(config)
    except ProjectConfigException as e:
        raise ProjectConfigException(
            f"{e}\n\nPlease check the configuration file: {config_path}"
        ) from None


class ProjectConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        use_attribute_docstrings=True,
    )

    template_version: int = 1
    """The project template version."""

    company_git_remote: str
    """The company github organization"""

    odoo_src_rel_path: Path
    """The path to the Odoo source code.

    For v1 projects, this is the path to the odoo/odoo submodule.
    For v2 projects, this is the path where both odoo/odoo and odoo/enterprise
    are located.
    """

    ext_src_rel_path: Path
    """The path to the external submodules are located."""

    local_src_rel_path: Path
    """The path to the local addons."""

    pending_merge_rel_path: Path
    """The path to the pending merges files."""

    version_file_rel_path: Path
    """The path to the version file."""

    marabunta_mig_file_rel_path: Path
    """The path to the Marabunta migration file."""


def get_conf_key(key):
    """Get a configuration key.

    Deprecated: use `load_config() and config.key` instead.

    .. code-block:: python

        conf = load_config()
        return conf.key

    """
    conf = load_config()
    return getattr(conf, key)
