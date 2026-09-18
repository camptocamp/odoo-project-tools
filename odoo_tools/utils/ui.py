# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import re
import shutil
import tempfile
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.progress import Progress, ProgressColumn, Task, TextColumn
from rich.spinner import Spinner
from rich.table import Column, Table
from rich.text import Text

from ..exceptions import Exit
from . import os_exec
from .click import DEFAULT_MAX_WORKERS, is_debug

# Rich console writing to stderr, for warnings/diagnostics that must not be
# mixed with a command's stdout (e.g. JSON output or a live-rendered table).
err_console = Console(stderr=True)


def exit_msg(msg):
    raise Exit(msg)


def warn(msg):
    """Print a warning on stderr, so it doesn't pollute a command's output."""
    err_console.print(f"Warning: {msg}", style="yellow")


def warn_missing_github_token():
    """Warn (on stderr) when no GITHUB_TOKEN is set.

    Unauthenticated GitHub API requests share a low rate limit and quickly
    start failing; commands that hit the API should call this up front.
    """
    if not os.environ.get("GITHUB_TOKEN"):
        warn(
            "GITHUB_TOKEN is not set; GitHub API requests "
            "are unauthenticated and may hit rate limits."
        )


def ask_confirmation(message):
    """Gently ask user's opinion."""
    r = input(message + " (y/N) ")
    return r in ("y", "Y", "yes")


def ask_or_abort(message):
    """Fail (abort) immediately if user disagrees."""
    if not ask_confirmation(message):
        exit_msg("Aborted")


def echo(msg, *pa, **kw):
    """Report a message to the user.

    While this thread's command output is being captured -- under
    :func:`run_tasks`, say -- the message goes to the capture too, landing in
    the running task's log rather than on the terminal. Anything written to the
    terminal there corrupts the live display drawn over it, so the rule is
    enforced here, once, for everything that reports through this module,
    rather than being one each call site has to remember.

    Note the distinction this makes explicit: ``ui.echo`` is a message *to* the
    user, and is redirected; a command's own output -- the Dockerfile
    addons-path, a JSON dump -- goes through ``click.echo`` and never is.

    Styling is dropped on the captured path: a log file has no colours, and
    :meth:`TaskProgress.write` strips them anyway.
    """
    sink = os_exec.current_output_sink()
    if sink is not None:
        # One call per line: the sink records a line at a time, and an embedded
        # newline would land in the tail as a single unrenderable blob. An
        # empty message is still the blank line the caller asked for.
        for line in str(msg).splitlines() or [""]:
            sink(line)
        return
    cmd = click.echo
    if kw.get("fg"):
        cmd = click.secho
    cmd(msg, *pa, **kw)


def ask_question(message, **prompt_kwargs):
    """Ask a question and return the answer

    Wrapper around ``click.prompt()``
    """
    return click.prompt(message, **prompt_kwargs)


# ── running tasks in parallel ────────────────────────────────────────────────


class TaskProgress:
    """The live state of a task run by :func:`run_tasks`.

    It is handed to the task itself, which says what it is up to through
    :meth:`set_status` and feeds it the output of the commands it runs through
    :meth:`write` -- landing both in the task's log file and, for the last
    lines, in the progress display.
    """

    def __init__(self, label: str, log_path: Path, tail_size: int = 1):
        self.label = label
        self.log_path = log_path
        self.status = ""
        self.status_is_outcome = False
        self.icon: Text | None = None
        self.hidden = False
        self.started_at: float | None = None
        self._tail: deque[str] = deque(maxlen=max(tail_size, 1))
        self._lock = threading.Lock()
        self._log_file = None

    def set_status(self, status: str) -> None:
        """Tell what the task is currently doing, in a word or two."""
        self.status = status
        self.status_is_outcome = False

    def set_outcome(
        self,
        outcome: str,
        *,
        icon: str | Text | None = None,
        hide: bool = False,
    ) -> None:
        """Tell what the task came to, in a word or two.

        Unlike a status, this stays on the row once the task is done: for work
        whose result is not simply "it went through" -- a pull request that was
        merged and dropped, against one still open -- the row is where that is
        read.

        :param icon: what to mark the row with instead of the tick, for a
            result that is worth telling apart at a glance.
        :param hide: drop the row from the display altogether, for a result
            that is worth recording and not worth reading -- a long run then
            collapses to the few rows that have something to say.

        Both apply once the task is done, and only if it went through: a
        failure keeps its row and its cross, since that row is the only place
        its reason and the link to its log are shown. Neither touches what the
        task reports anywhere else -- the outcome still reaches
        :class:`TaskResult` and the run's log either way.
        """
        self.status = outcome
        self.status_is_outcome = True
        self.icon = Text(icon) if isinstance(icon, str) else icon
        self.hidden = hide

    def write(self, line: str) -> str:
        """Record one line of output, as plain text, and return what was kept.

        Commands colour their output when they feel like it, whether or not
        anyone is watching -- git-aggregator does it unconditionally, git does
        it as soon as ``color.ui`` says so. Those bytes have to go before the
        line is shown: they count towards the width of the cell it is rendered
        in, so the message itself gets pushed out of view, and truncating in
        the middle of a sequence would emit an unterminated one to the terminal
        -- exactly the corruption the capture is there to avoid.

        ``Text.from_ansi`` handles all of it: it parses the escape sequences,
        drops the stray control codes as the ``Text`` is built, and keeps only
        what a carriage return would have left visible -- git reports progress
        by rewriting the line it is on.
        """
        line = Text.from_ansi(line).plain
        with self._lock:
            self._tail.append(line)
            if self._log_file is not None:
                self._log_file.write(line + "\n")
        return line

    def log(self, text: str) -> None:
        """Record text in the log file only, leaving the display alone.

        For detail that belongs in the log but not on a one-line row -- a
        traceback, say.
        """
        with self._lock:
            if self._log_file is not None:
                self._log_file.write(text if text.endswith("\n") else text + "\n")

    @property
    def tail(self) -> list[str]:
        """The last lines of output recorded, oldest first."""
        with self._lock:
            return list(self._tail)

    @property
    def elapsed(self) -> float:
        """Seconds since the task started, 0 if it hasn't yet."""
        if self.started_at is None:
            return 0.0
        return time.monotonic() - self.started_at

    @contextmanager
    def _collecting(self):
        """Collect what is written during this block into the log file."""
        with self.log_path.open("w") as log_file:
            with self._lock:
                self._log_file = log_file
            try:
                yield
            finally:
                with self._lock:
                    self._log_file = None


@dataclass
class TaskResult:
    """The outcome of a task run by :func:`run_tasks`."""

    label: str
    log_path: Path
    error: BaseException | None = None
    duration: float = 0.0
    #: What the task reported through :meth:`TaskProgress.set_outcome`, if it
    #: had something to say beyond having gone through.
    outcome: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None


class _TaskColumn(ProgressColumn):
    """A cell of the task table, rendered from the task itself.

    :class:`~rich.progress.TextColumn` covers a cell that is a piece of text;
    this one is for those that aren't, holding a spinner or a link.
    """

    def __init__(self, render_task: Callable[[Task], RenderableType], **column_options):
        self._render_task = render_task
        super().__init__(table_column=Column(**column_options))

    def render(self, task: Task):
        return self._render_task(task)


#: One spinner for every running row: rich renders it from the task's own
#: clock, and a fresh instance per frame would restart the animation.
#: One instance for the whole display: a fresh one per frame would restart
#: the animation, and two of them would drift out of phase.
SPINNER = Spinner("dots")


def _mark(ok: bool) -> Text:
    """How something went, in one character."""
    return Text("✔", style="green") if ok else Text("✖", style="red")


def _result_mark(result: TaskResult) -> Text:
    """How a finished task went, in one character."""
    return _mark(result.ok)


class Heading:
    """What a set of tasks is doing, on a line above the rows doing it.

    It carries the same spinner-then-mark a task row does, so a step of a
    command reads the way one of its tasks does: running, then done or failed.

    :param title: what the set is doing, in the present participle.
    """

    def __init__(self, title: str) -> None:
        self.title = title
        self.ok: bool | None = None

    def finish(self, ok: bool) -> None:
        """Settle the heading on an outcome, stopping the spinner."""
        self.ok = ok

    def __rich__(self) -> RenderableType:
        mark: RenderableType = (
            SPINNER.render(time.monotonic()) if self.ok is None else _mark(self.ok)
        )
        grid = Table.grid(padding=(0, 1))
        grid.add_row(mark, Text(self.title, style="bold"))
        return grid


def _worth_reading(result: TaskResult, keep_logs: bool) -> bool:
    """Whether a finished task's log is worth pointing the reader at.

    A failed task's log says what went wrong, and says it in full. A successful
    one's says nothing anybody wants, and is about to be thrown away -- unless
    the logs are being kept, and then it is there to be read.
    """
    return keep_logs or not result.ok


def _state_cell(task: Task) -> RenderableType:
    """A spinner while the task runs, then a tick, a cross, or the task's own
    mark -- see :meth:`TaskProgress.set_outcome`."""
    progress, result = task.fields["progress"], task.fields["result"]
    if result is None:
        return SPINNER.render(task.get_time())
    if result.ok and progress.icon is not None:
        return progress.icon
    return _result_mark(result)


def _log_link(result: TaskResult) -> Text:
    """A link to a task's log file, shown as the path itself.

    Written out in full so that it reads as a path; the column it lands in
    shortens it when there isn't room, and the link still targets the whole
    thing either way, a hyperlink's target being independent of the text it
    sits on.

    ``not dim`` because that column is dimmed, and a dimmed link reads as
    disabled rather than as something to click.

    The style goes on a span rather than on the whole ``Text``: a style set on
    the Text itself also covers the padding rich adds to fill the cell, which
    puts that padding inside the hyperlink and leaves terminals underlining the
    entire column.
    """
    log_path = result.log_path
    return Text.assemble((str(log_path), f"not dim bright_cyan link file://{log_path}"))


def _tail_cell(task: Task, keep_logs: bool) -> Text:
    """What a task has to show: its output, or the log to read about it."""
    result = task.fields["result"]
    if result is None:
        return Text("\n".join(task.fields["progress"].tail))
    # Done: whatever it was saying is of no further interest, and pointing at
    # the log beats repeating a truncated part of it here.
    return _log_link(result) if _worth_reading(result, keep_logs) else Text("")


def _status_cell(task: Task) -> Text:
    """What a task is doing, or what it came to.

    While it runs, the step it is on and how long it has been going. Once it is
    done: the step it went fine on is of no further interest, so only the time
    is left; the one it failed on very much is, so both are kept; and a task
    that reported through :meth:`TaskProgress.set_outcome` shows that alone,
    since a verdict is the point and how long it took to reach is not.
    """
    progress, result = task.fields["progress"], task.fields["result"]
    if result is not None and result.ok and progress.status_is_outcome:
        return Text(progress.status)
    elapsed = result.duration if result is not None else progress.elapsed
    status = "" if result is not None and result.ok else progress.status
    return Text(f"{status} {elapsed:.0f}s".strip())


def _log_file_names(labels) -> dict[str, str]:
    """Return a distinct, filesystem-safe log file name per label.

    A label may be anything, including a path, so it is sanitised -- which can
    map two labels onto the same name, and then onto the same file. Disambiguate
    with a counter rather than let one task's log silently overwrite another's.
    """
    names: dict[str, str] = {}
    used: set[str] = set()
    for label in labels:
        stem = re.sub(r"[^\w.-]+", "_", label) or "task"
        candidate = stem
        suffix = 2
        while candidate in used:
            candidate = f"{stem}-{suffix}"
            suffix += 1
        used.add(candidate)
        names[label] = f"{candidate}.log"
    return names


# The two below are what a run reports with no display to draw on. Everything
# goes through :class:`~rich.text.Text` rather than markup: these hold a label
# and the output of a command, and a stray ``[`` in either is not a style tag.


def _echoing_sink(progress: TaskProgress, console: Console) -> Callable[[str], object]:
    """A sink recording a task's output and echoing it as it comes.

    Prefixed with the task it belongs to, several of them being interleaved.
    """
    prefix = f"{progress.label}: "

    def report(line: str) -> None:
        line = progress.write(line)
        if line:
            # soft_wrap: these are log lines, and folding them to the width
            # would make paths and diffs unreadable.
            console.print(Text(prefix + line), soft_wrap=True)

    return report


def _print_outcome(console: Console, result: TaskResult, keep_logs: bool) -> None:
    """Say how a task went, there being no row of its own to say it on.

    The whole log path rather than a link, since there is nothing to click on;
    soft_wrap keeps it on one line, and so copyable.
    """
    outcome = f" {result.outcome}" if result.outcome else ""
    log = ""
    if _worth_reading(result, keep_logs):
        # A failure is reported *because* of its log; a success merely comes
        # with one.
        log = f" {result.log_path}" if result.ok else f": {result.log_path}"
    console.print(
        Text.assemble(
            _result_mark(result),
            f" {result.label}{outcome} ({result.duration:.0f}s){log}",
        ),
        soft_wrap=True,
    )


def run_tasks(
    tasks: Mapping[str, Callable[[TaskProgress], object]],
    max_workers: int = DEFAULT_MAX_WORKERS,
    tail_size: int = 1,
    keep_logs: bool | None = None,
    console: Console | None = None,
    title: str | None = None,
    exit_on_failure: bool = False,
) -> list[TaskResult]:
    """Run labelled tasks concurrently, displaying their progress live.

    Each task is called with its own :class:`TaskProgress` to report through,
    and gets its own log file collecting the output of the commands it runs:
    :func:`~.os_exec.run` and :func:`echo` are redirected there for the
    duration of the task, since anything reaching the terminal while the tasks
    run would corrupt the live display. Only those are, so a task must not
    write to stdout or stderr by any other means.

    Those logs live in a temporary directory of our own, thrown away once every
    task has succeeded -- there is nothing in them anybody wants by then. A
    failed task keeps its log and is reported with a link to it; ``keep_logs``
    keeps every log, successes included, and links those too, and defaults to
    whether the command was asked for debug output. Either way the
    path of each one is on its :class:`TaskResult`.

    A failing task doesn't stop the others: errors are captured and returned
    rather than raised, so the caller can report them all at once, at the end.
    How many failed is said once, at the bottom, whatever the caller does with
    the results -- each of them has already been reported on its own row, with
    a link to its own log, so the count is all that is left to say.

    :param title: what this set of tasks is doing, in the present participle.
        Shown above the rows, spinning until they have all finished and then
        settling on a tick or a cross. For a command made of several steps,
        where which one is running is worth saying.
    :param exit_on_failure: give up rather than return, once every failure has
        been reported. For a command whose exit code should say the run did not
        go through.
    :raises click.exceptions.Exit: if a task failed and ``exit_on_failure``.

    Without a terminal to draw a live display on there is no tail to watch, so
    every line is echoed as it arrives instead, prefixed with the label of the
    task it came from -- interleaved, but at least reported.

    :returns: a :class:`TaskResult` per task, in the order of ``tasks``.
    """
    # Outside a command nobody is going to go and read them, so they go.
    keep_logs = is_debug(default=False) if keep_logs is None else keep_logs
    console = console or Console()
    # No point drawing a display nobody can see; the output is then echoed
    # line by line instead.
    live_display = console.is_terminal
    heading = Heading(title) if title is not None else None
    if heading is not None and not live_display:
        console.print(title)
    log_dir = Path(tempfile.mkdtemp(prefix="otools-tasks-"))
    log_names = _log_file_names(tasks)
    progresses = {
        label: TaskProgress(label, log_dir / log_names[label], tail_size)
        for label in tasks
    }
    results: dict[str, TaskResult] = {}

    def run_task(label: str) -> TaskResult:
        progress = progresses[label]
        progress.started_at = time.monotonic()
        error = None
        # Where the task's output goes: its log file, plus the terminal itself
        # when there is no display to show it on.
        report = progress.write if live_display else _echoing_sink(progress, console)
        # Capturing the output here, rather than having the task pass a sink
        # down to every command it runs, is what keeps the whole call chain
        # unaware of the live display it must not write to.
        with progress._collecting(), os_exec.capture_output(report):
            try:
                tasks[label](progress)
            except BaseException as exc:
                error = exc
                progress.set_status("failed")
                report(str(exc))
                # The reason goes on the row, where there is room for one line;
                # the traceback goes to the log, which is what the row points
                # at. Without it a failure that isn't a command's own -- a bug
                # in here -- reads as a bare message with nothing to trace it
                # back to.
                progress.log("".join(traceback.format_exception(exc)))
        return TaskResult(
            label=label,
            log_path=progress.log_path,
            error=error,
            duration=progress.elapsed,
            outcome=progress.status if progress.status_is_outcome else "",
        )

    display = Progress(
        _TaskColumn(_state_cell),
        # markup=False: a label is a submodule name, not a style tag.
        TextColumn("{task.description}", markup=False),
        _TaskColumn(_status_cell, style="dim", no_wrap=True),
        _TaskColumn(
            lambda task: _tail_cell(task, keep_logs),
            style="dim",
            no_wrap=True,
            overflow="ellipsis",
            ratio=1,
        ),
        console=console,
        expand=True,
    )
    # The rows are rendered by a Live of our own rather than by the Progress
    # itself, so that the heading can sit above them and refresh with them.
    renderable = display if heading is None else Group(heading, display)
    live = (
        Live(renderable, console=console, refresh_per_second=10)
        if live_display
        else nullcontext()
    )
    try:
        with live:
            task_ids = {
                label: display.add_task(
                    label, total=None, progress=progresses[label], result=None
                )
                for label in tasks
            }
            try:
                # Not a context manager: on an interrupt the pool must be shut
                # down without waiting, and ThreadPoolExecutor.__exit__ always
                # waits.
                pool = ThreadPoolExecutor(max_workers=max_workers)
                futures = [pool.submit(run_task, label) for label in tasks]
                try:
                    for future in as_completed(futures):
                        result = future.result()
                        results[result.label] = result
                        display.update(
                            task_ids[result.label],
                            result=result,
                            visible=not (result.ok and progresses[result.label].hidden),
                        )
                        if not live_display:
                            _print_outcome(console, result, keep_logs)
                except BaseException:
                    # Interrupted. Worker threads can't be interrupted, but
                    # killing the commands they are waiting on makes them
                    # return; cancel first so that the ones which haven't
                    # started don't start now.
                    for future in futures:
                        future.cancel()
                    os_exec.terminate_running_processes()
                    pool.shutdown(wait=False)
                    raise
                # Everything has completed by now, so this doesn't block.
                pool.shutdown(wait=True)
            finally:
                # Inside the display, so that the frame it leaves behind has the
                # heading settled: a step cut short by an interrupt is one that
                # did not go through, and a spinner frozen mid-turn says
                # nothing.
                if heading is not None:
                    heading.finish(
                        len(results) == len(tasks)
                        and all(result.ok for result in results.values())
                    )
        if heading is not None and not live_display:
            # No frame was drawn for it, so the outcome of the step has to be
            # said the way each task's was.
            console.print(heading)
        outcomes = [results[label] for label in tasks]
        failures = [result for result in outcomes if not result.ok]
        if failures:
            console.print(
                f"[red]{len(failures)} task(s) failed. "
                "Please inspect the logs for details.[/]",
                highlight=False,
            )
            if exit_on_failure:
                # click's Exit rather than this project's: ours prints its own
                # message, and everything worth saying has been said.
                raise click.exceptions.Exit(1)
        return outcomes
    finally:
        if not keep_logs and all(result.ok for result in results.values()):
            # Either every task succeeded, or we were interrupted before any
            # outcome could be reported: nothing in there will ever be read.
            shutil.rmtree(log_dir, ignore_errors=True)
