# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
import subprocess
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner

from odoo_tools.utils import os_exec as exec_utils


def test_run():
    runner = CliRunner()
    with runner.isolated_filesystem():
        cwd = Path()
        assert not (cwd / "foo").exists()
        exec_utils.run("mkdir -p foo/bar")
        exec_utils.run("touch foo/bar/pippo.txt")
        assert (cwd / "foo/bar/pippo.txt").exists()


def test_has_exec():
    assert exec_utils.has_exec("ls")
    assert exec_utils.has_exec("pytest")
    assert not exec_utils.has_exec("this_does_not_exist")


# ── capture_output ────────────────────────────────────────────────────────────


def _collect(cmd, **kwargs):
    """Run a command with its output captured; return ``(result, lines)``."""
    lines = []
    with exec_utils.capture_output(lines.append):
        result = exec_utils.run(cmd, **kwargs)
    return result, lines


def test_capture_output_collects_stdout_lines_in_order():
    __, lines = _collect(["printf", "one\ntwo\nthree\n"])
    assert lines == ["one", "two", "three"]


def test_capture_output_writes_nothing_to_the_terminal(capfd):
    """The whole point: output goes to the sink, never to the terminal.

    Anything reaching the terminal would corrupt the live rendering the
    parallel aggregation draws on it.
    """
    _collect(["sh", "-c", "echo out; echo err >&2"])
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_capture_output_swallows_the_verbose_line_too(capfd):
    """`verbose` reports the command to the sink instead of printing it."""
    __, lines = _collect(["true"], verbose=True)
    assert lines == ["Running: true"]
    assert capfd.readouterr().out == ""


def test_verbose_still_prints_when_not_captured(capsys):
    exec_utils.run(["true"], verbose=True)
    assert "Running: true" in capsys.readouterr().out


def test_capture_output_raises_on_failure_with_check():
    with pytest.raises(subprocess.CalledProcessError):
        _collect(["sh", "-c", "echo boom >&2; exit 2"], check=True)


def test_capture_output_does_not_raise_without_check():
    __, lines = _collect(["sh", "-c", "echo boom >&2; exit 2"])
    assert lines == ["boom"]


def test_capture_output_runs_in_given_cwd(tmp_path):
    (tmp_path / "marker.txt").touch()
    __, lines = _collect(["ls"], cwd=tmp_path)
    assert lines == ["marker.txt"]


def test_capture_output_passes_env():
    __, lines = _collect(["sh", "-c", "echo $MY_VAR"], with_env={"MY_VAR": "hello"})
    assert lines == ["hello"]


def test_capture_output_does_not_leak_env_to_the_process(monkeypatch):
    """The command's environment must not be applied to our own process."""
    monkeypatch.delenv("MY_VAR", raising=False)
    monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)
    _collect(["true"], with_env={"MY_VAR": "hello"})
    assert "MY_VAR" not in os.environ
    assert "GIT_TERMINAL_PROMPT" not in os.environ


def test_capture_output_is_restored_afterwards():
    """Once the block is left, the sink stops receiving."""
    lines = []
    with exec_utils.capture_output(lines.append):
        exec_utils.run(["echo", "captured"])
    exec_utils.run(["echo", "not captured"])
    assert lines == ["captured"]


def test_capture_output_is_restored_after_a_failure():
    lines = []
    with pytest.raises(subprocess.CalledProcessError):
        with exec_utils.capture_output(lines.append):
            exec_utils.run(["false"], check=True)
    assert exec_utils._output_sink.get() is None


def test_capture_output_nests():
    outer, inner = [], []
    with exec_utils.capture_output(outer.append):
        with exec_utils.capture_output(inner.append):
            exec_utils.run(["echo", "inner"])
        exec_utils.run(["echo", "outer"])
    assert inner == ["inner"]
    assert outer == ["outer"]


def test_capture_output_is_per_thread():
    """Two tasks running at once must not land in each other's log."""
    first, second = [], []

    def task(sink, word, barrier):
        with exec_utils.capture_output(sink.append):
            barrier.wait()  # make sure both captures overlap
            exec_utils.run(["echo", word])

    barrier = threading.Barrier(2, timeout=10)
    threads = [
        threading.Thread(target=task, args=(first, "first", barrier)),
        threading.Thread(target=task, args=(second, "second", barrier)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert first == ["first"]
    assert second == ["second"]


def test_run_is_untouched_without_capture(capfd):
    """Outside a capture, run() behaves exactly as it always did."""
    assert exec_utils.run(["printf", "hello\n"]) == "hello"
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_current_output_sink_reports_the_active_one():
    """What lets something reporting *without* running a command honour the
    same capture -- see ui.echo."""
    lines = []
    sink = lines.append
    assert exec_utils.current_output_sink() is None
    with exec_utils.capture_output(sink):
        assert exec_utils.current_output_sink() is sink
    assert exec_utils.current_output_sink() is None


# ── quiet ─────────────────────────────────────────────────────────────────────


def test_run_quiet_writes_nowhere(capfd):
    __, lines = _collect(["sh", "-c", "echo out; echo err >&2"], quiet=True)
    assert lines == []
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_run_quiet_still_returns_the_output():
    """Silent is about where the output goes, not about losing it."""
    assert exec_utils.run(["printf", "hello\n"], quiet=True) == "hello"


def test_run_quiet_says_nothing_about_a_checked_failure(capfd):
    with pytest.raises(subprocess.CalledProcessError):
        exec_utils.run(["sh", "-c", "echo why >&2; exit 3"], check=True, quiet=True)
    captured = capfd.readouterr()
    assert "why" not in captured.out + captured.err


def test_run_quiet_swallows_the_verbose_line(capfd):
    exec_utils.run(["true"], verbose=True, quiet=True)
    assert capfd.readouterr().out == ""


def test_run_quiet_still_takes_the_other_options(tmp_path):
    (tmp_path / "marker.txt").touch()
    assert exec_utils.run(["ls"], cwd=tmp_path, quiet=True) == "marker.txt"


# ── one implementation, captured or not ───────────────────────────────────────


def test_run_returns_the_same_thing_captured_or_not():
    """There is a single implementation; capturing only adds a side channel."""
    cmd = ["sh", "-c", "echo first; echo second; echo noise >&2"]
    plain = exec_utils.run(cmd)
    lines = []
    with exec_utils.capture_output(lines.append):
        captured = exec_utils.run(cmd)
    assert plain == captured == "first\nsecond"
    assert sorted(lines) == ["first", "noise", "second"]


def test_run_never_lets_a_command_prompt():
    """Commands get no stdin, captured or not: a prompt could be unreachable."""
    assert exec_utils.run(["cat"]) == ""
    lines = []
    with exec_utils.capture_output(lines.append):
        assert exec_utils.run(["cat"]) == ""
    assert lines == []


def test_run_disables_git_prompts():
    assert exec_utils.run(["sh", "-c", "echo $GIT_TERMINAL_PROMPT"]) == "0"


def test_run_prints_stderr_on_failure_when_not_captured(capfd):
    """How a failure surfaces when nobody is collecting the output."""
    with pytest.raises(subprocess.CalledProcessError):
        exec_utils.run(["sh", "-c", "echo why it failed >&2; exit 3"], check=True)
    assert "why it failed" in capfd.readouterr().err


def test_run_does_not_print_stderr_on_failure_when_captured(capfd):
    """Captured, the sink already has it -- printing would break the display."""
    lines = []
    with pytest.raises(subprocess.CalledProcessError):
        with exec_utils.capture_output(lines.append):
            exec_utils.run(["sh", "-c", "echo why it failed >&2; exit 3"], check=True)
    assert lines == ["why it failed"]
    captured = capfd.readouterr()
    assert "why it failed" not in captured.out + captured.err


def test_run_failure_carries_the_output():
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        exec_utils.run(["sh", "-c", "echo out; echo err >&2; exit 3"], check=True)
    assert excinfo.value.returncode == 3
    assert excinfo.value.output == "out"
    assert excinfo.value.stderr == "err"


def test_run_does_not_raise_without_check():
    assert exec_utils.run(["sh", "-c", "echo out; exit 3"]) == "out"


# ── cleaning up the commands we start ─────────────────────────────────────────


def _pids_of(marker):
    """The pids of the still-running processes whose command mentions marker."""
    listing = subprocess.run(
        ["ps", "-Ao", "pid=,command="], capture_output=True, text=True
    ).stdout
    return [
        int(line.split(None, 1)[0])
        for line in listing.splitlines()
        if marker in line and "ps -Ao" not in line
    ]


def test_run_kills_the_command_when_the_sink_fails():
    """A failing sink must not leave the command running unsupervised."""
    marker = "otools-test-sink-failure"

    def exploding_sink(line):
        raise RuntimeError("the log is full")

    with pytest.raises(RuntimeError):
        with exec_utils.capture_output(exploding_sink):
            exec_utils.run(["sh", "-c", f"echo {marker}; sleep 30"])
    assert _pids_of(marker) == []


def test_terminate_running_processes_kills_the_whole_process_tree():
    """Commands spawn their own children, and those hold our pipes open.

    gitaggregate runs git, so signalling only the direct child leaves the
    worker blocked reading a pipe a grandchild still has open -- and a child
    forked just after the signal never received it at all.
    """
    marker = "otools-test-grandchild"
    started = threading.Event()
    finished = threading.Event()

    def target():
        with exec_utils.capture_output(lambda line: started.set()):
            try:
                # the outer shell stays alive, so the tree is a real tree
                exec_utils.run(
                    ["sh", "-c", f"sh -c 'sleep 30 # {marker}' & echo started; wait"],
                    check=True,
                )
            except subprocess.CalledProcessError:
                pass
            finally:
                finished.set()

    thread = threading.Thread(target=target)
    thread.start()
    assert started.wait(timeout=10), "the command never produced output"
    exec_utils.terminate_running_processes()
    assert finished.wait(timeout=10), "the worker was left blocked on a pipe"
    thread.join(timeout=10)
    assert _pids_of(marker) == [], "a grandchild outlived the command"


def test_terminate_running_processes_kills_a_running_command():
    """What the interrupt path relies on to unblock its worker threads."""
    marker = "otools-test-terminate"
    started = threading.Event()
    outcome = {}

    def target():
        with exec_utils.capture_output(lambda line: started.set()):
            try:
                exec_utils.run(["sh", "-c", f"echo {marker}; sleep 30"], check=True)
            except subprocess.CalledProcessError as exc:
                outcome["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    assert started.wait(timeout=10), "the command never produced output"
    exec_utils.terminate_running_processes()
    thread.join(timeout=10)
    assert not thread.is_alive(), "the command was not unblocked"
    assert _pids_of(marker) == []
    assert "error" in outcome


def test_run_decodes_as_utf8_whatever_the_locale_says():
    """The output is UTF-8; the locale must not corrupt what callers parse."""
    output = exec_utils.run(
        ["sh", "-c", "printf 'caf\\303\\251\\n'"],
        with_env={"LC_ALL": "C", "LANG": "C"},
    )
    assert output == "café"


# ── Command ───────────────────────────────────────────────────────────────────


def test_command_reports_how_it_went():
    """What run() throws away: the exit code, and stderr apart from stdout."""
    result = exec_utils.Command(["sh", "-c", "echo out; echo err >&2; exit 3"]).run()
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.args == ["sh", "-c", "echo out; echo err >&2; exit 3"]
    assert result.returncode == 3
    assert result.stdout == "out"
    assert result.stderr == "err"


def test_command_leaves_raising_to_the_caller():
    """A failing command is an answer here, not an exception. That is the
    point: asking `git remote get-url` whether a remote exists shouldn't cost
    a try/except -- and the caller who does want the exception still gets the
    one everything already catches."""
    result = exec_utils.Command(["false"]).run()
    assert result.returncode != 0
    with pytest.raises(subprocess.CalledProcessError):
        result.check_returncode()
    assert exec_utils.Command(["true"]).run().returncode == 0


def test_command_splits_a_string_command():
    assert exec_utils.Command("printf hello").argv == ["printf", "hello"]
    assert exec_utils.Command(["printf", "hello"]).argv == ["printf", "hello"]


def test_command_honours_the_ambient_capture():
    """The sink is not something the object knows about -- same contract as
    run(), since run() is only a way of saying this."""
    lines = []
    with exec_utils.capture_output(lines.append):
        exec_utils.Command(["sh", "-c", "echo out; echo err >&2"]).run()
    assert sorted(lines) == ["err", "out"]


def test_command_quiet_bypasses_the_capture(capfd):
    lines = []
    with exec_utils.capture_output(lines.append):
        result = exec_utils.Command(["sh", "-c", "echo out; echo err >&2"]).run(
            quiet=True
        )
    assert lines == []
    assert result.stdout == "out"
    assert result.stderr == "err"
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""
