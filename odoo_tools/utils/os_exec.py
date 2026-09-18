# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""Running system commands.

:class:`Command` is the primitive: it runs one command and reports how it went.
:func:`run` is the shorthand almost everything uses -- the output of a command
that is expected to work.

What this offers over :func:`subprocess.run` and :class:`subprocess.Popen`,
which the commands here would otherwise be spelled with:

* output is delivered a line at a time, as it arrives, to whatever
  :func:`capture_output` has set up. ``subprocess`` can hand back the output or
  let it through to the terminal, but not attribute it to a caller, and file
  descriptors are process-wide -- so a dozen commands running at once could not
  be told apart, and none of them could run behind a live display.
* commands cannot interact with the user: stdin is closed and git's prompts are
  disabled, so one waiting for an answer fails rather than hanging on input
  that may not be reachable.
* the virtualenv's ``bin`` is on ``PATH``, so console scripts installed
  alongside this one are found (see :func:`get_venv`).
* each command gets its own process group and is known to
  :func:`terminate_running_processes`, so an interrupt takes down the command
  and everything it spawned rather than orphaning it.
* output is decoded as UTF-8 whatever the locale says, since callers parse it.
"""

import contextvars
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import IO, cast

import click


def get_venv():
    """Return an environment that includes the virtualenv in the PATH

    When running otools from a virtualenv, where dependencies console scripts
    might not have been installed globally, we need make sure the PATH is set
    correctly so that the executables are found.
    """
    env_PATH = os.getenv("PATH")
    # If PATH is not set, we're likely running the tests
    if not env_PATH:
        return os.environ
    bin_path = Path(sys.executable).parent
    # If the bin_path is already there, perhaps this is a global install
    if str(bin_path) in env_PATH:
        return os.environ
    # Return a copy of the environment, with the venv bin path prepended to PATH
    env = os.environ.copy()
    env["PATH"] = f"{bin_path}:{env_PATH}"
    return env


#: Where the output of the commands run in the current thread should go, if
#: anywhere in particular. Set through :func:`capture_output` rather than
#: directly. A context variable rather than a global: with several commands
#: running at once, each one's output has to be attributable to its own task,
#: and file descriptors are process-wide so they can't tell them apart.
_output_sink: contextvars.ContextVar[Callable[[str], object] | None] = (
    contextvars.ContextVar("odoo_tools.output_sink", default=None)
)

#: How long a command is given to go away on its own before being killed.
KILL_GRACE_PERIOD = 2.0

#: Every command currently running, so that they can be killed on
#: interruption. See :func:`terminate_running_processes`.
_running_processes: set[subprocess.Popen] = set()
_running_processes_lock = threading.Lock()


@contextmanager
def _tracked(process: subprocess.Popen):
    """Keep ``process`` in the registry for as long as it is running."""
    with _running_processes_lock:
        _running_processes.add(process)
    try:
        yield
    finally:
        with _running_processes_lock:
            _running_processes.discard(process)


@contextmanager
def capture_output(on_line: Callable[[str], object]):
    """Send the output of every command run in this thread to ``on_line``.

    While this is active, :class:`Command` writes nothing to the terminal: each
    output line is handed to ``on_line`` instead, as it comes. That is what
    makes a command safe to run behind a live rendering, or from several
    threads at once, without every function in the call chain having to know
    about it.

    ``on_line`` may be called from another thread than this one, and is not
    called after the block exits.
    """
    token = _output_sink.set(on_line)
    try:
        yield
    finally:
        _output_sink.reset(token)


def current_output_sink() -> Callable[[str], object] | None:
    """Where this thread's command output is being sent, if anywhere.

    For the few places that report something without running a command: they
    have to honour the same capture, or their message lands on top of whatever
    is being rendered. See :func:`..ui.echo`.
    """
    return _output_sink.get()


def _command_env(with_env=None) -> dict[str, str]:
    """The environment a command runs in: ours, plus the venv, plus overrides."""
    env = dict(get_venv())
    # Never let git try to prompt: there may be no terminal to prompt on.
    env["GIT_TERMINAL_PROMPT"] = "0"
    if with_env:
        env.update(with_env)
    return env


class Command:
    """A system command, ready to be run.

    Commands never get to interact with the user: stdin is closed and git's
    prompts are disabled, so one waiting for an answer fails instead of hanging
    on input that may not even be reachable -- it could be running behind a
    live display, or next to a dozen others. Their output goes to whatever
    :func:`capture_output` has set up, rather than to the terminal directly.

    What the command *is* is fixed here; how one execution of it *reports* is
    up to :meth:`run`.

    :param cmd: the command to execute, as a string or a preparsed list
    :param cwd: the working directory to run it in, or None
    :param env: environment variables to set on top of the inherited ones
    """

    def __init__(
        self,
        cmd: str | Sequence[str],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.argv: list[str] = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
        self.cwd = cwd
        self.env = env

    def run(
        self, *, verbose: bool = False, quiet: bool = False
    ) -> subprocess.CompletedProcess[str]:
        """Run to completion and report how it went.

        A non-zero exit code is not an error here: it is in the result, for the
        caller to make of what it will. Call
        :meth:`~subprocess.CompletedProcess.check_returncode` on the result to
        turn it into the exception instead.

        stderr is streamed along with stdout when the output is being captured
        (see :func:`capture_output`), but the two are kept apart in the result:
        plenty of callers parse stdout.

        :param verbose: if True, report the command before running it.
        :param quiet: if True, the output goes nowhere at all -- not to the
            terminal, and not to an active capture either. For the commands
            that are questions, where a non-zero exit is one of the answers
            rather than something gone wrong and git saying so is not worth
            reporting.
        """
        # Resolved once, here, before anything starts: the stderr pump runs on
        # its own thread, where the context variable behind it is not set.
        on_line = None if quiet else current_output_sink()
        # `not quiet` again: with no sink, announcing falls back to the
        # terminal, which is the one place a quiet command must not reach.
        if verbose and not quiet:
            self._announce(on_line)
        process = self._spawn()
        # Both are set, since we asked for pipes.
        stdout = cast(IO[str], process.stdout)
        stderr = cast(IO[str], process.stderr)
        with _tracked(process):
            try:
                stdout_lines, stderr_lines = self._pump(stdout, stderr, on_line)
                returncode = process.wait()
            except BaseException:
                # Interrupted, or the sink itself failed. Never leave the
                # command running: it would keep going unsupervised, holding
                # our pipes.
                kill_process_trees([process])
                raise
            finally:
                stdout.close()
                stderr.close()
        return subprocess.CompletedProcess(
            self.argv,
            returncode,
            "\n".join(stdout_lines),
            "\n".join(stderr_lines),
        )

    def _announce(self, on_line: Callable[[str], object] | None) -> None:
        """Report the command, wherever this thread's output is going."""
        message = f"Running: {shlex.join(self.argv)}"
        if on_line is not None:
            on_line(message)
        else:
            click.echo(click.style(message, fg="bright_black"))

    def _spawn(self) -> subprocess.Popen:
        return subprocess.Popen(
            self.argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_command_env(self.env),
            cwd=self.cwd,
            text=True,
            # Decode as UTF-8 whatever the locale says: the output of the
            # commands we run is UTF-8, and the caller may well be parsing it.
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            # Own process group, so that the whole tree can be killed: commands
            # spawn their own children (gitaggregate runs git), and those
            # inherit our pipes, so killing only the direct child leaves us
            # blocked on a pipe a grandchild still holds open.
            start_new_session=True,
        )

    def _pump(
        self,
        stdout: IO[str],
        stderr: IO[str],
        on_line: Callable[[str], object] | None,
    ) -> tuple[list[str], list[str]]:
        """Drain both pipes, handing each line to ``on_line`` as it comes."""
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def pump(stream, collect):
            for line in stream:
                line = line.rstrip("\n")
                collect.append(line)
                if on_line is not None:
                    on_line(line)

        # stderr is drained by its own thread: reading the two pipes in
        # sequence would deadlock as soon as the command fills the one nobody
        # is reading.
        stderr_pump = threading.Thread(
            target=pump, args=(stderr, stderr_lines), daemon=True
        )
        stderr_pump.start()
        pump(stdout, stdout_lines)
        stderr_pump.join()
        return stdout_lines, stderr_lines


def run(cmd, check=False, with_env=None, verbose=False, cwd=None, quiet=False):
    """Execute a system command and return its stdout, stripped.

    The short way to say :meth:`Command.run`, and what most callers want: the
    output of a command that is expected to work. Reach for :class:`Command`
    itself when the exit code is an answer rather than a failure.

    :param cmd: the command to execute, as a string or a preparsed list
    :param check: if True, raise on a non-zero exit code.
    :param with_env: a dictionary of environment variables to set, or None.
        The legacy spelling of :class:`Command`'s ``env``.
    :param verbose: if True, report the command before running it.
    :param cwd: the working directory to run the command in, or None.
    :param quiet: if True, the output goes nowhere at all -- see
        :meth:`Command.run`.
    :raises subprocess.CalledProcessError: on a non-zero exit code, when ``check``.
    """
    result = Command(cmd, cwd=cwd, env=with_env).run(verbose=verbose, quiet=quiet)
    if check and result.returncode:
        if result.stderr and not quiet and current_output_sink() is None:
            # Nobody is watching the output, so surface the reason ourselves.
            print(result.stderr, file=sys.stderr)
        result.check_returncode()
    return result.stdout.strip()


def _signal_tree(process: subprocess.Popen, process_group, signal_number: int):
    """Signal a process group, or the command alone if it never got one."""
    if process_group is not None:
        try:
            os.killpg(process_group, signal_number)
            return
        except (ProcessLookupError, PermissionError):
            pass  # the group is empty, or not ours to signal
    try:
        process.send_signal(signal_number)
    except (ProcessLookupError, PermissionError, ValueError):
        pass  # already reaped


def kill_process_trees(processes):
    """Kill commands and everything they spawned, then reap them.

    The whole process group of each one is signalled -- see the
    ``start_new_session`` in :meth:`Command._spawn` -- because the children a
    command spawns inherit our pipes, so killing the command alone leaves us
    blocked reading a pipe they still hold open. Reaping the command is not
    enough to know they are gone either: one forked just after the first signal
    never received it, and is simply reparented when its parent dies. Hence the
    unconditional SIGKILL sweep.

    Every command is signalled before any of them is waited on, so the grace
    period is spent once rather than once per command.
    """
    # Resolve the groups up front: reaping a command frees its pid, and with it
    # the only handle on the children it may have left behind.
    targets = []
    for process in processes:
        try:
            targets.append((process, os.getpgid(process.pid)))
        except (ProcessLookupError, PermissionError):
            targets.append((process, None))
    for signal_number in (signal.SIGTERM, signal.SIGKILL):
        for process, process_group in targets:
            _signal_tree(process, process_group, signal_number)
        deadline = time.monotonic() + KILL_GRACE_PERIOD
        for process, __ in targets:
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=max(0.0, deadline - time.monotonic()))


def terminate_running_processes():
    """Kill every command currently running, and everything they spawned.

    Meant for cleaning up on interruption: a thread blocked on a command's
    output can't be interrupted, but killing the command makes it return.
    """
    with _running_processes_lock:
        processes = list(_running_processes)
    kill_process_trees(processes)


def has_exec(name):
    return bool(shutil.which(name))
