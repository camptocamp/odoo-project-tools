# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import annotations

import configparser
import sys
from functools import cache, cached_property
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
from ruamel.yaml import YAMLError

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from ..exceptions import ProjectConfigException
from .misc import parse_ini_cfg
from .path import build_path
from .yaml import yaml_load

# Legacy configuration files, still read during the transition period, with
# [tool.odoo-project] taking precedence over them. The configuration used to be
# split between the tool settings (.proj.cfg) and the project manifest
# (.cookiecutter.context.yml); both are merged into a single ProjectConfig.
# TODO: Remove when all projects are migrated
DEPRECATED_PROJ_CFG_PATH = ".proj.cfg"
DEPRECATED_MANIFEST_PATH = ".cookiecutter.context.yml"

# The unified configuration lives under [tool.odoo-project] in pyproject.toml.
PYPROJECT_SECTION = "odoo-project"


def read_pyproject_section() -> dict | None:
    """Return the ``[tool.odoo-project]`` table from the project pyproject.toml.

    Returns ``None`` when the file or the section is absent, so callers can fall
    back to the legacy configuration files during the transition period.
    """
    try:
        content = build_path("pyproject.toml").read_text()
    except FileNotFoundError:
        return None
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as e:
        raise ProjectConfigException(f"Unable to parse pyproject.toml: {e}") from None
    return data.get("tool", {}).get(PYPROJECT_SECTION)


def read_legacy_proj_cfg(path: Path) -> dict:
    """Return the settings of the legacy ``.proj.cfg`` file."""
    try:
        return dict(parse_ini_cfg(path.read_text(), "conf")["conf"])
    except configparser.Error as e:
        raise ProjectConfigException(
            f"Unable to parse {DEPRECATED_PROJ_CFG_PATH}: {e}"
        ) from None


def read_legacy_manifest(path: Path) -> dict:
    """Return the values of the legacy ``.cookiecutter.context.yml`` file."""
    try:
        data = yaml_load(path.read_text())
    except YAMLError as e:
        raise ProjectConfigException(
            f"Unable to parse {DEPRECATED_MANIFEST_PATH}: {e}"
        ) from None
    # An empty file reads as None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ProjectConfigException(
            f"Unable to parse {DEPRECATED_MANIFEST_PATH}: expected a mapping"
        )
    return dict(data)


@cache
def warn_deprecated_config_source() -> None:
    """Warn (once) that the legacy configuration files are deprecated.

    Emitted when configuration is read from ``.proj.cfg``, or from
    ``.cookiecutter.context.yml`` in a project without a
    ``[tool.odoo-project]`` section in its ``pyproject.toml``.
    """
    # Imported here: ui imports click, which imports minimum_version, which
    # imports this module.
    from . import ui

    ui.err_console.print(
        "WARNING: reading configuration from .proj.cfg / "
        ".cookiecutter.context.yml is deprecated. Define a [tool.odoo-project] "
        "section in pyproject.toml instead.",
        style="yellow",
        # Printed as is: [tool.odoo-project] would be taken for markup
        markup=False,
    )


def format_pydantic_validation_error(e: ValidationError) -> str:
    """Format a Pydantic validation error."""
    messages = []
    for error in e.errors():
        fname = error["loc"][0]
        message = f"- '{fname}': {error['msg']}"
        field = ProjectConfig.model_fields.get(str(fname))
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


def read_config_sources() -> tuple[dict, list[str]]:
    """Read and layer the project configuration sources, without validating.

    Every source is layered over the previous one, field by field, so each
    only has to declare what it overrides:

    1. the defaults of :class:`ProjectConfig`,
    2. the legacy ``.proj.cfg`` tool settings,
    3. the legacy ``.cookiecutter.context.yml`` project manifest,
    4. the ``[tool.odoo-project]`` section of the project root
       ``pyproject.toml``.

    Reading ``.proj.cfg`` emits a deprecation warning, and so does reading the
    manifest of a project without a ``[tool.odoo-project]`` section. Next to
    the section, the manifest is read silently: it belongs to the project
    template, which keeps it around.

    :returns: the layered values, and a description of each source read
    """
    config = {}
    sources = []
    # The legacy configuration files are still supported for a transition
    # period, until all projects declare a [tool.odoo-project] section in their
    # pyproject.toml.
    # TODO: Remove when all projects are migrated
    section = read_pyproject_section()
    legacy_path = build_path(DEPRECATED_PROJ_CFG_PATH)
    if legacy_path.exists():
        config.update(read_legacy_proj_cfg(legacy_path))
        sources.append(DEPRECATED_PROJ_CFG_PATH)
        warn_deprecated_config_source()
    manifest_path = build_path(DEPRECATED_MANIFEST_PATH)
    if manifest_path.exists():
        config.update(read_legacy_manifest(manifest_path))
        sources.append(DEPRECATED_MANIFEST_PATH)
        if section is None:
            warn_deprecated_config_source()
    if section is not None:
        config.update(section)
        sources.append("the [tool.odoo-project] section in pyproject.toml")
    if not sources:
        raise ProjectConfigException(
            "Missing [tool.odoo-project] section in pyproject.toml."
        )
    return config, sources


def load_config() -> ProjectConfig:
    """Loads the project configuration, as layered by :func:`read_config_sources`."""
    config, sources = read_config_sources()
    try:
        return validate_config(config)
    except ProjectConfigException as e:
        raise ProjectConfigException(
            f"{e}\n\nPlease check the configuration: {', '.join(sources)}"
        ) from None


def falsy_to_none(v: Any) -> Any | None:
    if not v:
        return None
    return v


OptionalPath = Annotated[Path | None, BeforeValidator(falsy_to_none)]
OptionalStr = Annotated[str | None, BeforeValidator(falsy_to_none)]


class ProjectConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        use_attribute_docstrings=True,
        # YAML and TOML read unquoted values such as ``project_id: 1289`` or
        # ``odoo_version: 16.0`` as numbers.
        coerce_numbers_to_str=True,
    )

    # TODO: proj_tmpl_ver=2 is deprecated
    template_version: int = 1
    """The project template version."""

    company_git_remote: str = "camptocamp"
    """The company github organization"""

    odoo_src_rel_path: Path = Path("odoo/src")
    """The path to the Odoo source code.

    For v1 projects, this is the path to the odoo/odoo submodule.
    For v2 projects (deprecated), this is the path where both odoo/odoo and
    odoo/enterprise are located.
    """

    ext_src_rel_path: Path = Path("odoo/external-src")
    """The path to the external submodules are located."""

    local_src_rel_path: Path = Path("odoo/local-src")
    """The path to the local addons."""

    pending_merge_rel_path: Path = Path("pending-merges.d")
    """The path to the pending merges files."""

    # The optional paths have no default: when unset, consumers fall back to
    # other sources (e.g. the bundle addon version) instead of reading a file
    # that may not exist.
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

    odoo_version: str
    """The project's Odoo version, e.g. ``16.0``."""

    customer_shortname: str
    """Short name of the customer, e.g. used to build the bundle addon name."""

    project_name: OptionalStr = None
    """The project name."""

    project_id: OptionalStr = None
    """The internal company's project ID.

    Used by ``otools-submodule`` to configure targeted fetch refspecs and by
    ``otools-pending`` to name merge branches.
    """

    country: OptionalStr = None
    """The customer's country code, e.g. ``ch``."""

    odoo_main_lang: OptionalStr = None
    """The main Odoo language, e.g. ``de_DE``."""

    odoo_aux_langs: OptionalStr = None
    """The auxiliary Odoo languages, separated by commas or semicolons, e.g.
    ``fr_CH,it_IT``.
    """

    @property
    def odoo_serie(self) -> int:
        """The Odoo major version number, derived from ``odoo_version``.

        For example ``16`` for ``odoo_version = "16.0"``.
        """
        return int(self.odoo_version.split(".")[0])

    def require(self, name: str) -> Any:
        """Return the value of an optional setting the caller cannot do without.

        Raises :class:`ProjectConfigException` naming the setting when it is not
        set, rather than letting the caller carry on with ``None``.
        """
        value = getattr(self, name)
        if value is None:
            raise ProjectConfigException(
                f"'{name}' is not set in the project configuration."
            )
        return value

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

    @cached_property
    def _config(self) -> ProjectConfig:
        return load_config()

    def _reload(self):
        self.__dict__.pop("_config", None)

    def __getattr__(self, name):
        return getattr(self._config, name)


config = LazyConfig()
