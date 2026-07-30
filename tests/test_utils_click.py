# Copyright 2026 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import click
import pytest

from odoo_tools.utils.click import (
    global_command_decorators,
    handle_exceptions,
    is_debug,
)


@pytest.fixture(autouse=True)
def restore_logging():
    """Keep the global logging state out of the other tests.

    The `--debug` flag configures logging process-wide, which would otherwise
    leak from one test to the next.
    """
    package_logger = logging.getLogger("odoo_tools")
    level = package_logger.level
    root_handlers = logging.getLogger().handlers[:]
    yield
    package_logger.setLevel(level)
    logging.getLogger().handlers[:] = root_handlers


@pytest.fixture()
def cli():
    """A CLI wired like the real ``otools-*`` ones."""

    @click.group()
    @global_command_decorators
    def cli():
        pass

    @cli.command()
    @handle_exceptions()
    def emit():
        logging.getLogger("odoo_tools.utils.testing").debug("a debug message")
        logging.getLogger("urllib3.connectionpool").debug("third-party message")

    @cli.command()
    @handle_exceptions()
    def boom():
        raise ValueError("kaboom")

    @cli.command()
    def probe():
        click.echo(f"debug={is_debug()}")

    return cli


def test_is_debug_without_a_context():
    """Outside of any command the flag could not have been parsed yet."""
    assert is_debug() is True


def test_is_debug_is_false_by_default(cli, runner):
    result = runner.invoke(cli, ["probe"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "debug=False" in result.output


def test_is_debug_reads_the_global_flag(cli, runner):
    result = runner.invoke(cli, ["--debug", "probe"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "debug=True" in result.output


def test_is_debug_reads_a_command_option(runner):
    """A command exposing its own `debug` param is honoured too."""

    @click.command()
    @click.option("--debug", is_flag=True)
    def probe(debug):
        click.echo(f"debug={is_debug()}")

    result = runner.invoke(probe, ["--debug"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "debug=True" in result.output


def test_debug_option_is_available(cli, runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "--debug" in result.output


def test_debug_logs_are_hidden_by_default(cli, runner, caplog):
    result = runner.invoke(cli, ["emit"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "a debug message" not in caplog.text


def test_debug_option_enables_package_debug_logs(cli, runner, caplog):
    result = runner.invoke(cli, ["--debug", "emit"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "a debug message" in caplog.text
    # The level is raised on our own logger only, so that third-party debug
    # output (urllib3 & friends) stays out of the way.
    assert "third-party message" not in caplog.text


def test_debug_option_sets_up_a_log_handler(cli, runner, monkeypatch):
    """The flag must also give the logs somewhere to go.

    Raising the level is not enough: without a handler the records are
    discarded. That part cannot be asserted on the captured stderr, because
    pytest has already put a handler on the root logger, which makes
    `basicConfig` a no-op for the whole test suite.
    """
    calls = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: calls.append(kwargs))
    result = runner.invoke(cli, ["--debug", "emit"], catch_exceptions=False)
    assert result.exit_code == 0
    assert calls


def test_handle_exceptions_wraps_errors_by_default(cli, runner):
    result = runner.invoke(cli, ["boom"])
    assert result.exit_code == 1
    assert "Failed to boom: kaboom" in result.output


def test_debug_option_reraises_errors(cli, runner):
    """The flag reaches `handle_exceptions` even though it is not exposed."""
    result = runner.invoke(cli, ["--debug", "boom"])
    assert isinstance(result.exception, ValueError)
