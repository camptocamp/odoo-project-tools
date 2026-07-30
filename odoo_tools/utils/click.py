import logging
from collections.abc import Callable
from functools import wraps

import click

from .. import __version__
from .minimum_version import with_minimum_version_check
from .update_check import with_update_check

__all__ = [
    "DEFAULT_MAX_WORKERS",
    "debug_option",
    "deprecated_option",
    "handle_exceptions",
    "global_command_decorators",
    "is_debug",
    "jobs_option",
    "version_option",
    "with_minimum_version_check",
    "with_update_check",
]

#: Key under which the ``--debug`` flag is stored in the click context meta.
#: ``Context.meta`` is shared by the whole context tree, so a nested command
#: can read the flag whether it was passed to the group or to the command.
DEBUG_META_KEY = "odoo_tools.debug"


def is_debug() -> bool:
    """Tell whether debug mode is currently on.

    Debug mode shows full stack traces (see `handle_exceptions`) and routes the
    ``odoo_tools`` debug logs to stderr.

    With no click context at all, debug mode is reported: we are then running
    outside of a command, early enough that the flag could not have been parsed
    yet, and being verbose about whatever goes wrong is the more useful default
    there.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return True
    return bool(
        # Set by the global `--debug` flag, wherever it was passed
        ctx.meta.get(DEBUG_META_KEY)
        # Check the current context (e.g: command options)
        or ctx.params.get("debug")
        # Check the root context (e.g: global options)
        or ctx.find_root().params.get("debug")
    )


def deprecated_option(*param_decls, message: str | None = None, **kwargs):
    """``click.option`` variant that rejects use with a deprecation message.

    The option is hidden from ``--help``, accepts no value, and exits with
    a friendly error pointing the user at the replacement.

    Usage:

    .. code-block:: python

        @deprecated_option("--purge", message="Use `... clean` instead.")
        def show_pending(...):
            ...
    """

    def callback(ctx, param, value):
        if value:
            raise click.BadOptionUsage(
                param.opts[0],
                message or f"`{param.opts[0]}` has been removed.",
                ctx=ctx,
            )

    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("default", False)
    kwargs["hidden"] = True
    kwargs["expose_value"] = False
    kwargs["callback"] = callback
    return click.option(*param_decls, **kwargs)


version_option = click.version_option(
    __version__, "-V", "--version", package_name="odoo-tools"
)

#: How much concurrency this project considers reasonable, by default.
DEFAULT_MAX_WORKERS = 8

#: Shared ``--jobs`` option for the commands that fan their work out over a
#: thread pool. Pass it as ``max_workers``; ``--jobs 1`` runs everything
#: sequentially, which is handy to get readable output or to debug a failure.
jobs_option = click.option(
    "--jobs",
    "jobs",
    type=click.IntRange(min=1),
    default=DEFAULT_MAX_WORKERS,
    show_default=True,
    help="Number of operations to run in parallel.",
)


def _enable_debug(ctx, param, value):
    """Turn debug mode on as soon as the flag is parsed.

    Debug mode both shows full stack traces (see `handle_exceptions`) and
    routes the ``odoo_tools`` debug logs to stderr. The level is raised on our
    own logger rather than on the root one, to keep third-party debug output
    (urllib3 & friends) out of the way.
    """
    ctx.meta[DEBUG_META_KEY] = value
    if value:
        logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
        logging.getLogger("odoo_tools").setLevel(logging.DEBUG)
    return value


#: The flag is eager so that logging is ready before any other callback runs,
#: and unexposed so that it does not reach the command callbacks, which mostly
#: take no argument at all.
debug_option = click.option(
    "--debug",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_enable_debug,
    help="Show full stack traces and log debug messages.",
)


def global_command_decorators(func):
    """Apply the standard ``otools-*`` pre-invoke hooks.

    Bundles (in order): update-available check, project ``otools_min_version``
    enforcement, the ``-V`` / ``--version`` flag and the ``--debug`` flag.
    Place it right above ``def cli(...):`` so it wraps the callback;
    ``@click.group()`` / ``@click.command()`` and any CLI-specific options stay
    where they are.
    """
    func = with_update_check(func)
    func = with_minimum_version_check(func)
    func = version_option(func)
    func = debug_option(func)
    return func


def handle_exceptions() -> Callable:
    """Decorator to handle exceptions and print a nice error message.

    If `debug` is set in the context, the function is run without catching
    exceptions so that the full stack trace is shown.
    Otherwise, the exception is caught and a short error message is printed.

    The flag comes from `global_command_decorators`, so it only needs to wrap
    the command itself, e.g:

    .. code-block:: python

        @click.group()
        @global_command_decorators
        def cli():
            ...

        @click.command()
        @handle_exceptions()
        def my_command():
            ...

    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # If debug mode is enabled, run the function without catching exceptions
            if is_debug():
                return func(*args, **kwargs)
            # Otherwise, catch the exception and print a short error message
            try:
                return func(*args, **kwargs)
            except Exception as e:
                raise click.ClickException(f"Failed to {func.__name__}: {e}") from e

        return wrapper

    return decorator
