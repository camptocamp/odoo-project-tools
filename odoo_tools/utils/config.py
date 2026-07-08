# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import annotations

import os
from functools import cached_property
from os import PathLike
from pathlib import Path
from textwrap import indent
from typing import Annotated, Any

from packaging.version import InvalidVersion, Version
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    ValidationError,
    field_validator,
)

from ..exceptions import ProjectConfigException
from .misc import parse_ini_cfg
from .path import build_path

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
            f"The configuration is malformed.\n\n{format_pydantic_validation_error(e)}"
        ) from None


def load_config(config_path: PathLike) -> ProjectConfig:
    """Loads the configuration file."""
    try:
        content = build_path(config_path, from_root=True).read_text()
        config = dict(parse_ini_cfg(content, "conf")["conf"])
    except FileNotFoundError as e:
        raise ProjectConfigException(e) from e
    try:
        return validate_config(config)
    except ProjectConfigException as e:
        raise ProjectConfigException(
            f"{e}\n\nPlease check the configuration file: {config_path}"
        ) from None


def falsy_to_none(v: Any) -> Any | None:
    if not v:
        return None
    return v


OptionalPath = Annotated[Path | None, BeforeValidator(falsy_to_none)]


class ProjectConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        use_attribute_docstrings=True,
    )

    # TODO: proj_tmpl_ver=2 is deprecated
    template_version: int = 1
    """The project template version."""

    company_git_remote: str
    """The company github organization"""

    odoo_src_rel_path: Path
    """The path to the Odoo source code.

    For v1 projects, this is the path to the odoo/odoo submodule.
    For v2 projects (deprecated), this is the path where both odoo/odoo and
    odoo/enterprise are located.
    """

    ext_src_rel_path: Path
    """The path to the external submodules are located."""

    local_src_rel_path: Path
    """The path to the local addons."""

    pending_merge_rel_path: Path
    """The path to the pending merges files."""

    version_file_rel_path: OptionalPath = None
    """The path to the version file."""

    marabunta_mig_file_rel_path: OptionalPath = None
    """The path to the Marabunta migration file."""

    otools_min_version: Annotated[str | None, BeforeValidator(falsy_to_none)] = None
    """The minimum required version of odoo-tools to operate on this project.

    If set, any ``otools-*`` command will refuse to run when the installed
    version is lower than this one. Useful to enforce a baseline on shared
    projects. Example: ``otools_min_version = 0.14.0``.
    """

    @field_validator("otools_min_version")
    @classmethod
    def _validate_otools_min_version(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            Version(v)
        except InvalidVersion as exc:
            raise ValueError(f"not a valid version string: {v!r}") from exc
        return v


class LazyConfig:
    """Lazy configuration loader"""

    def __init__(self, config_path: PathLike | str):
        self._config_path = Path(config_path)

    @cached_property
    def _config(self) -> ProjectConfig:
        return load_config(self._config_path)

    def _reload(self):
        self.__dict__.pop("_config", None)

    def __getattr__(self, name):
        return getattr(self._config, name)


config = LazyConfig(PROJ_CFG_FILE)
