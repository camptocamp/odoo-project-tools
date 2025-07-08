from functools import wraps
from typing import Callable

import click


def handle_exceptions() -> Callable:
    """Decorator to handle exceptions and print a nice error message.

    If `debug` is set in the context, the function is run without catching
    exceptions so that the full stack trace is shown.
    Otherwise, the exception is caught and a short error message is printed.

    It can be used to wrap any click.command, e.g:

    .. code-block:: python

        @click.group()
        @click.option("--debug", is_flag=True)
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
            debug = (
                # If ctx is None, it may be an early stage so we treat as debug mode
                (ctx := click.get_current_context(silent=True)) is None
                # Check the current context (e.g: command options)
                or ctx.params.get("debug")
                # Check the root context (e.g: global options)
                or ctx.find_root().params.get("debug")
            )
            # If debug mode is enabled, run the function without catching exceptions
            if debug:
                return func(*args, **kwargs)
            # Otherwise, catch the exception and print a short error message
            try:
                return func(*args, **kwargs)
            except Exception as e:
                raise click.ClickException(f"Failed to {func.__name__}: {e}") from e

        return wrapper

    return decorator
