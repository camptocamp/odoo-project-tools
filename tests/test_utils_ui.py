# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import re
import threading
import time
from pathlib import Path
from unittest import mock

import click
import pytest

from odoo_tools.utils import os_exec, ui

from .common import plain_console, terminal_console


def _plain(text: str) -> str:
    """A captured frame without the styling or the cursor moves, for asserting
    on what it says."""
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text)


# ── run_tasks ─────────────────────────────────────────────────────────────────


def _noop_task(progress):
    """A task that does nothing, and so succeeds."""


def _failing_task(progress):
    raise RuntimeError("nope")


def test_run_tasks_returns_a_result_per_task_in_order():
    results = ui.run_tasks(
        {
            "edi": _noop_task,
            "web": _noop_task,
            "stock": _noop_task,
        },
        console=plain_console(),
    )
    assert [result.label for result in results] == ["edi", "web", "stock"]
    assert all(result.ok for result in results)


def test_run_tasks_runs_tasks_concurrently():
    """Tasks overlap: each one waits for the others to have started."""
    started = threading.Barrier(3, timeout=10)

    def task(progress):
        started.wait()

    results = ui.run_tasks(
        {name: task for name in ("edi", "web", "stock")},
        max_workers=3,
        console=plain_console(),
    )
    # A timeout on the barrier would have been captured as a task error.
    assert all(result.ok for result in results)


def test_run_tasks_captures_failures_without_stopping_the_others():
    results = ui.run_tasks(
        {"edi": _failing_task, "web": _noop_task},
        console=plain_console(),
    )
    edi, web = results
    assert not edi.ok
    assert isinstance(edi.error, RuntimeError)
    assert str(edi.error) == "nope"
    assert web.ok


def _echoing_task(progress):
    os_exec.run(["sh", "-c", "echo to stdout; echo to stderr >&2"])


def test_run_tasks_captures_the_output_of_the_commands_a_task_runs(capfd):
    """A task's commands land in its log without the task arranging anything.

    This is what spares every function in the call chain from carrying a sink
    around just because it might run under a live display.
    """
    (result,) = ui.run_tasks(
        {"edi": _echoing_task}, keep_logs=True, console=plain_console()
    )
    assert result.ok
    assert sorted(result.log_path.read_text().splitlines()) == [
        "to stderr",
        "to stdout",
    ]
    capfd.readouterr()  # drain what was echoed, asserted on below


def test_the_output_never_reaches_a_terminal_showing_the_display(capfd):
    """Written raw it would corrupt the live display it is drawn over."""
    (result,) = ui.run_tasks(
        {"edi": _echoing_task}, keep_logs=True, console=terminal_console()
    )
    assert result.ok
    captured = capfd.readouterr()
    assert "to stdout" not in captured.out + captured.err
    assert "to stderr" not in captured.out + captured.err


def test_the_output_is_echoed_as_it_comes_when_there_is_no_display(capfd):
    """No tail to watch, so the lines themselves are the progress report.

    Prefixed with the task they came from, since several tasks interleave.
    """
    ui.run_tasks({"edi": _echoing_task, "web": _echoing_task}, console=plain_console())
    printed = capfd.readouterr().out
    for label in ("edi", "web"):
        assert f"{label}: to stdout" in printed
        assert f"{label}: to stderr" in printed


def test_the_reason_a_task_failed_is_echoed_too(capfd):
    """Otherwise a failure in CI reports only a path nobody can open."""

    def boom(progress):
        os_exec.run(
            ["sh", "-c", "echo 'fatal: no such remote' >&2; exit 128"], check=True
        )

    ui.run_tasks({"edi": boom}, console=plain_console())
    printed = capfd.readouterr().out
    assert "edi: fatal: no such remote" in printed
    assert "edi: " in printed and "128" in printed


def test_run_tasks_keeps_each_task_output_in_its_own_log():
    """Concurrent tasks must not leak into each other's log."""
    in_flight = threading.Barrier(2, timeout=10)

    def make_task(word):
        def task(progress):
            in_flight.wait()  # guarantee the two captures overlap
            os_exec.run(["echo", word])

        return task

    results = ui.run_tasks(
        {"edi": make_task("edi-output"), "web": make_task("web-output")},
        max_workers=2,
        keep_logs=True,
        console=plain_console(),
    )
    assert all(result.ok for result in results)
    for result in results:
        assert result.log_path.read_text() == f"{result.label}-output\n"


def test_run_tasks_restores_the_capture_afterwards(capsys):
    ui.run_tasks({"edi": _noop_task}, console=plain_console())
    os_exec.run(["true"], verbose=True)
    assert "Running: true" in capsys.readouterr().out


def test_run_tasks_writes_a_log_file_per_task():
    def task(progress):
        progress.write("hello")
        progress.write("world")

    results = ui.run_tasks(
        {"edi": task, "web": task}, keep_logs=True, console=plain_console()
    )
    assert len({result.log_path for result in results}) == 2
    for result in results:
        assert result.log_path.read_text() == "hello\nworld\n"


def test_run_tasks_keeps_the_log_of_a_failing_task():
    def task(progress):
        progress.write("about to fail")
        raise RuntimeError("nope")

    (result,) = ui.run_tasks({"edi": task}, console=plain_console())
    assert not result.ok
    # what the task wrote, and then the reason it stopped: the log is where the
    # reader is sent, so it has to say why
    assert result.log_path.read_text().startswith("about to fail\nnope\n")


def test_the_log_of_a_failing_task_carries_the_traceback():
    """The row has room for the reason; the log is where you find out where it
    came from -- which a failure that isn't a command's own really needs."""

    def task(progress):
        {}["missing"]

    (result,) = ui.run_tasks({"edi": task}, console=plain_console())
    log = result.log_path.read_text()
    # the reason first, then where it came from
    assert log.startswith("'missing'\nTraceback (most recent call last):\n")
    assert "test_utils_ui.py" in log and "in task" in log
    assert '{}["missing"]' in log
    assert log.rstrip().endswith("KeyError: 'missing'")


def test_run_tasks_log_file_name_is_safe():
    """A label may be a path; it must not be taken as one for the log file."""
    results = ui.run_tasks(
        {"odoo/external-src/edi": _noop_task},
        keep_logs=True,
        console=plain_console(),
    )
    assert results[0].log_path.name == "odoo_external-src_edi.log"
    assert results[0].log_path.exists()


def test_run_tasks_reports_outcomes_when_not_a_terminal():
    console = plain_console()
    with console.capture() as capture:
        __, failed = ui.run_tasks(
            {"edi": _noop_task, "web": _failing_task},
            max_workers=1,
            console=console,
        )
    output = capture.get()
    assert "✔ edi" in output
    assert "✖ web" in output
    # no terminal to click on, so the whole path is what's printed
    assert str(failed.log_path) in output


def test_run_tasks_throws_the_logs_away_when_every_task_succeeded():
    """Nobody wants the logs of a run where nothing went wrong."""
    (result,) = ui.run_tasks({"edi": _noop_task}, console=plain_console())
    assert not result.log_path.exists()
    assert not result.log_path.parent.exists()


def test_run_tasks_keeps_the_logs_when_a_task_failed():
    """Including the logs of the tasks that went fine: they are one run."""

    ok, failed = ui.run_tasks(
        {"edi": _noop_task, "web": _failing_task},
        max_workers=1,
        console=plain_console(),
    )
    assert failed.log_path.exists()
    assert ok.log_path.exists()


def test_run_tasks_keeps_the_logs_when_asked_to():
    (result,) = ui.run_tasks(
        {"edi": _noop_task}, keep_logs=True, console=plain_console()
    )
    assert result.log_path.exists()


# ── TaskProgress ──────────────────────────────────────────────────────────────


def test_task_progress_tail_keeps_the_last_lines():
    def task(progress):
        for i in range(5):
            progress.write(f"line {i}")
        # the tail is what the display shows, the log keeps everything
        assert progress.tail == ["line 3", "line 4"]

    (result,) = ui.run_tasks(
        {"edi": task}, tail_size=2, keep_logs=True, console=plain_console()
    )
    assert result.ok
    assert result.log_path.read_text().splitlines() == [f"line {i}" for i in range(5)]


def test_task_progress_reports_status_and_duration():
    seen = {}

    def task(progress):
        progress.set_status("aggregating")
        seen["status"] = progress.status
        time.sleep(0.02)
        seen["elapsed"] = progress.elapsed

    (result,) = ui.run_tasks({"edi": task}, console=plain_console())
    assert seen["status"] == "aggregating"
    # the clock actually runs, rather than staying on its 0.0 default
    assert seen["elapsed"] >= 0.02
    assert result.duration >= 0.02


# ── reporting a failure ───────────────────────────────────────────────────────


def test_a_failed_task_row_points_at_its_log():
    """The failure and where to read about it are reported in one place.

    Saying it once on the row and again in a summary is what made a single
    failed submodule read as two.
    """

    console = terminal_console()
    with console.capture() as capture:
        (result,) = ui.run_tasks({"edi": _failing_task}, console=console)
    frame = capture.get()
    assert "✖" in frame
    # only the file name is shown, but the link opens the full path: a
    # hyperlink's target is independent of the text it is on
    assert result.log_path.name in frame
    assert f"file://{result.log_path}" in frame
    # the reason is not repeated on the row: the log it links to is where the
    # caller is expected to have put it
    assert "nope" not in frame


# ── the terminal path ─────────────────────────────────────────────────────────
#
# What the display actually renders, which the non-interactive path never
# exercises. `git-aggregator` colours its output unconditionally, so these
# lines are what the feature really has to cope with.

GITAGGREGATE_LINE = (
    "\x1b[0m\x1b[32m\x1b[1m(INFO)\x1b[0m [\x1b[30m\x1b[2m\x1b[1m08:43:15\x1b[39m\x1b[0m] "
    "\x1b[37m\x1b[2m\x1b[1mgit_aggregator.repo\x1b[39m\x1b[0m  "
    "\x1b[34m\x1b[2m\x1b[1medi \x1b[39m\x1b[0m \x1b[0m Start aggregation of edi"
)
GITAGGREGATE_PLAIN = (
    "(INFO) [08:43:15] git_aggregator.repo  edi   Start aggregation of edi"
)


def _render_frames(capsys, line, width=100):
    """Return what the display drew while a task was emitting ``line``.

    The task stays alive for a few refreshes on purpose: what it was saying is
    cleared from its row once it finishes, so a frame drawn afterwards would
    show nothing to assert on. Read through pytest rather than
    ``Console.capture()`` because rich's capture buffer is thread-local, so the
    frames its refresh thread draws would not land in it.
    """
    console = terminal_console(width=width, interactive=True)

    def task(progress):
        progress.write(line)
        time.sleep(0.3)  # ~3 frames at the default 10 per second

    ui.run_tasks({"edi": task}, console=console)
    return capsys.readouterr().out


def test_the_tail_shows_the_message_of_a_coloured_line(capsys):
    """The point of the tail: seeing what the command is doing.

    A line dressed in escape codes must still be readable -- those bytes count
    towards the cell width, so left in place they push the message out of view.
    """
    frames = _render_frames(capsys, GITAGGREGATE_LINE)
    assert "Start aggregation of edi" in frames


def test_the_tail_emits_no_escape_sequence_of_its_own(capsys):
    """Truncating a coloured line must not leave a half-written sequence.

    An unterminated CSI reaching the terminal is exactly the corruption the
    capture exists to prevent, and it is what truncating mid-sequence produces.
    """
    # narrow enough that the line has to be cut short
    frames = _render_frames(capsys, GITAGGREGATE_LINE, width=60)
    # rich's own styling is fine; the command's must be gone
    assert "\x1b[32m" not in frames.replace("\x1b[32m✔", "")
    assert "\x1b[30m" not in frames
    assert "\x1b[39m" not in frames
    assert "…" in frames  # it really was truncated


def test_the_frame_shows_every_task_with_its_state():
    def boom(progress):
        progress.write("it went wrong")
        raise RuntimeError("nope")

    console = terminal_console()
    with console.capture() as capture:
        ui.run_tasks(
            {"edi": lambda progress: progress.write("all good"), "web": boom},
            max_workers=1,
            console=console,
        )
    frame = capture.get()
    assert "edi" in frame and "web" in frame
    assert "✔" in frame and "✖" in frame
    # the failing task points at its log; the one that went fine has nothing
    # left worth saying
    assert "web.log" in frame
    assert "all good" not in frame.rsplit("✔", 1)[-1]


@pytest.mark.parametrize(
    ("written", "recorded"),
    [
        pytest.param("plain text", "plain text", id="plain"),
        pytest.param("keeps\ttabs", "keeps\ttabs", id="tabs-kept"),
        pytest.param("café", "café", id="non-ascii-kept"),
        pytest.param(GITAGGREGATE_LINE, GITAGGREGATE_PLAIN, id="coloured"),
        # git reports progress by rewriting the line with a carriage return,
        # and only the last rewrite is what it would have been left showing --
        # nothing at all, for a line that ends on one. Not that run() ever
        # hands one over: it reads in text mode, so a carriage return has
        # already ended the line by then.
        pytest.param("50%\r75%\r100%", "100%", id="several-crs"),
        pytest.param("Receiving objects:  50%\r", "", id="rewritten-away"),
        # not every control character comes as part of an escape sequence
        pytest.param("oops\x08\x07 done\x1b[0m", "oops done", id="bare-controls"),
    ],
)
def test_what_a_task_writes_is_recorded_as_plain_text(written, recorded):
    """Escape codes help neither a human reading the log nor the display."""
    (result,) = ui.run_tasks(
        {"edi": lambda progress: progress.write(written)},
        keep_logs=True,
        console=plain_console(),
    )
    assert result.log_path.read_text() == f"{recorded}\n"


def test_run_tasks_log_names_stay_distinct_when_sanitised():
    """Two labels sanitising to one name must not share a log file."""
    results = ui.run_tasks(
        {
            "a/b": lambda progress: progress.write("from a/b"),
            "a_b": lambda progress: progress.write("from a_b"),
        },
        keep_logs=True,
        console=plain_console(),
    )
    paths = {result.log_path for result in results}
    assert len(paths) == 2
    contents = sorted(path.read_text().strip() for path in paths)
    assert contents == ["from a/b", "from a_b"]


def test_run_tasks_reports_a_task_killed_by_a_base_exception():
    """A BaseException from one task must not discard everyone's result."""

    def interrupted(progress):
        raise KeyboardInterrupt

    results = ui.run_tasks(
        {"edi": interrupted, "web": lambda progress: progress.write("fine")},
        max_workers=1,
        console=plain_console(),
    )
    assert [(r.label, r.ok) for r in results] == [("edi", False), ("web", True)]
    assert isinstance(results[0].error, KeyboardInterrupt)


def test_a_finished_task_stops_showing_its_output():
    """Nothing it said matters once it went fine, so the row goes quiet."""
    console = terminal_console()
    with console.capture() as capture:
        (result,) = ui.run_tasks(
            {"edi": lambda progress: progress.write("chatting away")},
            console=console,
        )
    last_frame = capture.get().rsplit("✔", 1)[-1]
    assert "chatting away" not in last_frame
    assert result.log_path.name not in last_frame


def test_a_finished_task_links_its_log_when_the_logs_are_kept():
    """With --debug the logs stay around, so they are worth pointing at."""
    console = terminal_console()
    with console.capture() as capture:
        (result,) = ui.run_tasks(
            {"edi": lambda progress: progress.write("chatting away")},
            keep_logs=True,
            console=console,
        )
    frame = capture.get()
    assert result.log_path.name in frame
    assert f"file://{result.log_path}" in frame


def test_the_log_of_a_success_is_reported_only_when_asked():
    """With no display to draw on, and nothing to click, the whole path."""

    def report(keep_logs):
        console = plain_console()
        with console.capture() as capture:
            (result,) = ui.run_tasks(
                {"edi": _noop_task},
                keep_logs=keep_logs,
                console=console,
            )
        return capture.get(), result

    output, result = report(keep_logs=False)
    assert output.strip() == f"✔ edi ({result.duration:.0f}s)"
    output, result = report(keep_logs=True)
    assert output.strip() == f"✔ edi ({result.duration:.0f}s) {result.log_path}"


def test_a_log_link_covers_the_path_and_nothing_else():
    """The padding rich adds to fill the cell must stay out of the hyperlink.

    Inside it, terminals underline the whole column instead of just the path,
    and the row reads as one big link.
    """

    # wide enough for the whole path, so that what is inside the link is the
    # path and not an ellipsised part of it
    console = terminal_console(width=400)
    with console.capture() as capture:
        (result,) = ui.run_tasks({"edi": _failing_task}, console=console)
    frame = capture.get()
    # everything between the end of the hyperlink's opener and its terminator
    opener_end = frame.index("\x1b\\", frame.index("\x1b]8;")) + 2
    linked = frame[opener_end : frame.index("\x1b]8;;", opener_end)]
    assert _plain(linked) == str(result.log_path)
    # bright cyan, and neither dimmed (2) nor underlined (4) by us: the
    # underline on a link is the terminal's own doing
    codes = re.findall(r"\x1b\[([0-9;]*)m", linked)[0].split(";")
    assert "96" in codes
    assert "2" not in codes and "4" not in codes


def test_the_status_of_a_failure_survives_on_the_row():
    """The step a task went fine on is dropped once it is done; the step it
    failed on is kept, so a status set while handling the failure still shows.
    """

    def boom(progress):
        progress.set_status("pushing")
        raise RuntimeError("nope")

    console = terminal_console(width=400)
    with console.capture() as capture:
        ui.run_tasks(
            {"edi": lambda progress: progress.set_status("pushing"), "web": boom},
            max_workers=1,
            console=console,
        )
    last_frame = capture.get().rsplit("✔", 1)[-1]
    # run_tasks() sets it to "failed" itself, on top of whatever the task said
    assert "failed" in last_frame
    # ...and the successful row says nothing about the step it ended on
    assert "pushing" not in last_frame.split("✖")[0]


# ── echo, while a task's output is captured ───────────────────────────────────


def test_echo_reaches_the_task_log_and_never_the_terminal(capfd):
    """The helpers a task calls report through ui.echo without knowing it runs
    behind a live display -- so echo has to honour the capture, or the message
    lands on top of the frame being drawn."""

    def task(progress):
        ui.echo("Updating submodule edi")

    (result,) = ui.run_tasks({"edi": task}, keep_logs=True, console=terminal_console())
    assert result.ok
    assert result.log_path.read_text() == "Updating submodule edi\n"
    captured = capfd.readouterr()
    assert "Updating submodule edi" not in captured.out + captured.err


def test_echo_drops_the_colour_when_captured():
    """A log file has no colours, and the tail strips them anyway."""

    def task(progress):
        ui.echo("WARNING: fetch failed", fg="yellow")

    (result,) = ui.run_tasks({"edi": task}, keep_logs=True, console=plain_console())
    assert result.log_path.read_text() == "WARNING: fetch failed\n"


def test_echo_records_a_multiline_message_one_line_at_a_time():
    """The sink records a line at a time; an embedded newline would land in the
    tail as a single unrenderable blob."""

    def task(progress):
        ui.echo("first\nsecond")
        assert progress.tail == ["second"]

    (result,) = ui.run_tasks({"edi": task}, keep_logs=True, console=plain_console())
    assert result.ok
    assert result.log_path.read_text() == "first\nsecond\n"


def test_echo_keeps_a_blank_line():
    def task(progress):
        ui.echo("")

    (result,) = ui.run_tasks({"edi": task}, keep_logs=True, console=plain_console())
    assert result.log_path.read_text() == "\n"


def test_echo_still_prints_when_nothing_is_capturing(capsys):
    """The other ~60 callers, which run outside any task, are unaffected."""
    ui.echo("plain as ever")
    assert capsys.readouterr().out == "plain as ever\n"


# ── reporting the failures, and giving up on them ─────────────────────────────


def test_run_tasks_says_how_many_failed():
    """Each of them was reported on its own row; the count is what's left."""
    console = plain_console()
    with console.capture() as capture:
        ui.run_tasks(
            {"edi": _failing_task, "web": _failing_task, "stock": _noop_task},
            max_workers=1,
            console=console,
        )
    output = capture.get()
    assert "2 task(s) failed" in output
    assert "Please inspect the logs for details." in output


def test_run_tasks_says_nothing_when_none_failed():
    console = plain_console()
    with console.capture() as capture:
        ui.run_tasks({"edi": _noop_task}, console=console)
    assert "failed" not in capture.get()


def test_run_tasks_returns_the_failures_rather_than_raising_by_default():
    """The default suits a caller that means to carry on regardless."""
    results = ui.run_tasks(
        {"edi": _failing_task, "web": _noop_task}, console=plain_console()
    )
    assert [result.ok for result in results] == [False, True]


def test_run_tasks_gives_up_on_a_failure_when_asked():
    with pytest.raises(click.exceptions.Exit) as excinfo:
        ui.run_tasks(
            {"edi": _failing_task}, console=plain_console(), exit_on_failure=True
        )
    assert excinfo.value.exit_code == 1


def test_run_tasks_keeps_the_log_of_a_run_it_gave_up_on():
    """Giving up must not take the log the message just pointed at with it."""
    console = plain_console()
    with console.capture() as capture, pytest.raises(click.exceptions.Exit):
        ui.run_tasks({"edi": _failing_task}, console=console, exit_on_failure=True)
    (path,) = re.findall(r"(\S+edi\.log)", capture.get())
    assert Path(path).exists()


# ── run_tasks: the heading ────────────────────────────────────────────────────


def test_run_tasks_shows_the_title_above_the_rows():
    console = terminal_console()
    with console.capture() as capture:
        ui.run_tasks(
            {"edi": _noop_task}, console=console, title="Aggregating submodules"
        )
    output = _plain(capture.get())
    assert "Aggregating submodules" in output
    # The heading is the first thing said, and the rows come under it.
    assert output.index("Aggregating submodules") < output.index("edi")


@pytest.mark.parametrize(
    ("tasks", "mark"),
    [
        ({"edi": _noop_task}, "✔"),
        ({"edi": _failing_task}, "✖"),
        # one failure among many is still a failed step
        ({"edi": _noop_task, "web": _failing_task}, "✖"),
    ],
)
def test_run_tasks_heading_settles_on_the_outcome(tasks, mark):
    console = terminal_console()
    with console.capture() as capture:
        ui.run_tasks(tasks, console=console, title="Aggregating")
    assert f"{mark} Aggregating" in _plain(capture.get())


def test_run_tasks_says_the_title_without_a_terminal():
    """There is no heading to draw, but which step is running still matters."""
    console = plain_console()
    with console.capture() as capture:
        ui.run_tasks({"edi": _noop_task}, console=console, title="Aggregating")
    assert "Aggregating" in capture.get()


def test_run_tasks_draws_no_heading_without_a_title():
    console = terminal_console()
    with console.capture() as capture:
        ui.run_tasks({"edi": _noop_task}, console=console)
    assert _plain(capture.get()).strip().startswith("✔ edi")


def test_run_tasks_reports_the_step_outcome_without_a_terminal():
    """No frame is drawn for the heading on a pipe, so the step says how it
    went the way each of its tasks does -- a CI log that announces a step and
    never comes back to it is the one place this matters most."""
    console = plain_console()
    with console.capture() as capture:
        ui.run_tasks({"edi": _failing_task}, console=console, title="Aggregating")
    output = capture.get()
    assert output.startswith("Aggregating")
    assert "✖ Aggregating" in output


def test_a_status_is_dropped_once_the_task_went_fine():
    """The step a task was on says nothing once it is done."""
    console = terminal_console()

    def task(progress):
        progress.set_status("updating")

    with console.capture() as capture:
        ui.run_tasks({"edi": task}, console=console)
    assert "updating" not in _plain(capture.get())


def test_an_outcome_stays_on_the_row():
    """Unlike a step, what the task came to is the thing worth reading -- for
    work whose result is not simply that it went through."""
    console = terminal_console()

    def task(progress):
        progress.set_status("checking")
        progress.set_outcome("merged, removed")

    with console.capture() as capture:
        ui.run_tasks({"OCA/edi#773": task}, console=console)
    output = _plain(capture.get())
    assert "merged, removed" in output
    assert "checking" not in output


# ── set_outcome: how a finished row reads, or whether it reads at all ─────────


def _hiding_task(progress):
    progress.set_status("checking")
    progress.set_outcome("open, kept", hide=True)


def _dotted_task(progress):
    progress.set_outcome("merged, removed", icon="●")


def test_a_hidden_row_leaves_the_display_and_its_neighbours_stay():
    console = terminal_console()
    with console.capture() as capture:
        ui.run_tasks(
            {"OCA/edi#773": _hiding_task, "OCA/web#112": _dotted_task},
            console=console,
        )
    frame = _plain(capture.get())
    assert "OCA/edi#773" not in frame
    assert "OCA/web#112" in frame


def test_an_icon_replaces_the_tick_for_a_task_that_asked_for_one():
    console = terminal_console()
    with console.capture() as capture:
        ui.run_tasks({"OCA/web#112": _dotted_task, "edi": _noop_task}, console=console)
    frame = _plain(capture.get())
    assert "● OCA/web#112" in frame
    # a task that asked for nothing is marked the way it always was
    assert "✔ edi" in frame


def test_a_failure_keeps_its_row_its_cross_and_its_log_whatever_it_asked_for():
    """The row is the only place a failure's reason and its log are shown, so
    neither request is honoured for one."""

    def task(progress):
        progress.set_outcome("merged, removed", icon="●", hide=True)
        raise RuntimeError("403 rate limit exceeded")

    console = terminal_console()
    with console.capture() as capture:
        results = ui.run_tasks({"OCA/web#112": task}, console=console)
    frame = _plain(capture.get())
    assert "✖ OCA/web#112" in frame
    assert "●" not in frame
    assert Path(results[0].log_path).name in frame


def test_neither_request_changes_what_the_run_reports():
    """They are about the display; the record is untouched."""
    (result,) = ui.run_tasks(
        {"OCA/edi#773": _hiding_task}, console=plain_console(), keep_logs=True
    )
    assert result.ok
    assert result.outcome == "open, kept"
    assert result.log_path.exists()


def test_a_row_that_will_be_hidden_is_drawn_while_it_runs(capsys):
    """Hiding is about the finished row: the work still has to be watchable.

    The other half -- that it is gone once the task is done -- is
    ``test_a_hidden_row_leaves_the_display_and_its_neighbours_stay``, whose
    non-interactive console captures exactly the final frame.
    """
    console = terminal_console(interactive=True)

    def task(progress):
        progress.set_status("checking")
        time.sleep(0.3)  # ~3 frames at the default 10 per second
        progress.set_outcome("open, kept", hide=True)

    ui.run_tasks({"OCA/edi#773": task}, console=console)
    frames = _plain(capsys.readouterr().out)
    assert "OCA/edi#773 checking" in frames


def test_an_outcome_is_shown_instead_of_the_duration():
    """How long a verdict took to reach is not the point; how long a clone took
    very much is, so a task that reported nothing keeps its timing."""
    console = terminal_console()
    with console.capture() as capture:
        ui.run_tasks(
            {"OCA/web#112": _dotted_task, "odoo/src": _noop_task}, console=console
        )
    frame = _plain(capture.get())
    assert "● OCA/web#112 merged, removed" in frame
    assert re.search(r"OCA/web#112.*\ds", frame) is None
    assert re.search(r"✔ odoo/src\s+\ds", frame) is not None


def test_a_failure_keeps_its_state_and_its_duration():
    """Even one that had already reported an outcome: a verdict it did not live
    to deliver must not stand in for how it went."""

    def task(progress):
        progress.set_outcome("merged, removed", icon="●")
        raise RuntimeError("disk full")

    console = terminal_console()
    with console.capture() as capture:
        ui.run_tasks({"OCA/web#112": task}, console=console)
    frame = _plain(capture.get())
    assert re.search(r"✖ OCA/web#112\s+failed \ds", frame) is not None
    assert "merged, removed" not in frame


def test_the_duration_still_reaches_a_run_without_a_terminal():
    """Dropping it is about the row, not about the record."""
    console = plain_console()
    with console.capture() as capture:
        ui.run_tasks({"OCA/web#112": _dotted_task}, console=console)
    assert re.search(r"✔ OCA/web#112 merged, removed \(\ds\)", capture.get())


def test_the_logs_are_kept_in_debug_mode_without_being_asked():
    """Every caller used to pass `keep_logs=is_debug()`; run_tasks reads it."""
    with mock.patch.object(ui, "is_debug", return_value=True):
        (result,) = ui.run_tasks({"edi": _noop_task}, console=plain_console())
    assert result.log_path.exists()


def test_the_logs_go_when_there_is_no_command_to_have_asked():
    """Outside a command `is_debug()` reports debug mode, which would leave a
    temporary directory behind on every call that is not a CLI run."""
    (result,) = ui.run_tasks({"edi": _noop_task}, console=plain_console())
    assert not result.log_path.exists()
