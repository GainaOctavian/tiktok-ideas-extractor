from datetime import date

import pytest

from app.commands import COMMANDS, parse_line, run_script
from app.jobs import Jobs
from pipeline.report import status_lines
from tests.test_jobs import GatedFakes
from tests.test_runner import Fakes


@pytest.fixture
def jobs(cfg):
    return Jobs(cfg, make_steps=Fakes([1, 2]).steps)


def run(text, cfg, jobs):
    return run_script(text, cfg, jobs)


def test_parse_line():
    assert parse_line("  run momentumcash 5 ") == ["run", "momentumcash", "5"]
    assert parse_line('status "@cont"') == ["status", "@cont"]
    assert parse_line("   ") is None
    assert parse_line("# a comment") is None
    assert parse_line("RUN cont") == ["run", "cont"]


def test_help_lists_every_command(cfg, jobs):
    out, code = run("help", cfg, jobs)
    assert code == 0
    for name in COMMANDS:
        assert name in out


def test_unknown_command_stops_script(cfg, jobs):
    out, code = run("help\nfly cont\nstate", cfg, jobs)
    assert code == 1
    lines = out.splitlines()
    assert lines[-1] == "error at line 2 (fly cont): unknown command 'fly' (try: help)"
    assert len(lines) == len(COMMANDS) + 1  # help ran, state did not


@pytest.mark.parametrize(
    "line, reason",
    [
        ("run cont abc", "limit must be a whole number of at least 1"),
        ("run cont 0", "limit must be a whole number of at least 1"),
        ("run 'bad name!'", "Not a TikTok account"),
        ("run", "missing account"),
        ("status a b", "too many arguments"),
    ],
)
def test_argument_errors(cfg, jobs, line, reason):
    out, code = run(line, cfg, jobs)
    assert code == 1 and reason in out and out.startswith("error at line 1")


def test_run_wait_end_to_end(cfg, jobs):
    out, code = run("run @Cont 1\nwait\nstate", cfg, jobs)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "started @cont (limit 1)"
    assert lines[1].startswith("@cont: 1 done")
    assert lines[2] == "idle"
    assert lines[3].startswith("last: @cont: 1 done")


def test_run_twice_is_an_error(cfg):
    fakes = GatedFakes([1, 2])
    jobs = Jobs(cfg, make_steps=fakes.steps)
    run("run cont", cfg, jobs)
    assert fakes.entered.wait(5)
    out, code = run("run cont", cfg, jobs)
    assert code == 1 and "a run is already active" in out
    out, _ = run("state", cfg, jobs)
    assert out.startswith("running @cont")
    out, code = run("reset cont", cfg, jobs)
    assert code == 1 and "stop the run first" in out
    out, _ = run("stop\nstate", cfg, jobs)
    assert out.splitlines()[0] == "stopping after the current clip"
    assert out.splitlines()[1].endswith("(stopping)")
    fakes.gate.set()
    jobs.wait(5)


def test_stop_when_idle(cfg, jobs):
    assert run("stop", cfg, jobs) == ("nothing running", 0)


def test_status_export_reset_match_reports(cfg, jobs):
    run("run cont\nwait", cfg, jobs)
    out, _ = run("status cont", cfg, jobs)
    assert out.splitlines() == status_lines("cont", cfg)
    out, _ = run("export cont", cfg, jobs)
    assert out.splitlines()[-1] == "2 clips exported"
    out, _ = run("exports", cfg, jobs)
    assert out.startswith(f"cont-{date.today().isoformat()}") and "KB" in out
    assert run("reset cont", cfg, jobs) == ("0 failed clips requeued", 0)


def test_exports_when_none(cfg, jobs):
    assert run("exports", cfg, jobs) == ("no exports", 0)


def test_log(cfg, jobs):
    run("run cont\nwait", cfg, jobs)
    out, _ = run("log 2", cfg, jobs)
    assert len(out.splitlines()) == 2 and out.splitlines()[0].startswith("[2/2]")
