import threading

import pytest

from app.jobs import Busy, Jobs
from pipeline.lister import ListingError
from tests.test_runner import Fakes


class GatedFakes(Fakes):
    """Fakes whose OCR blocks until released, so a run can be observed mid-flight."""

    def __init__(self, ids):
        super().__init__(ids)
        self.gate = threading.Event()
        self.entered = threading.Event()

    def ocr_frame(self, path, cfg):
        self.entered.set()
        assert self.gate.wait(5), "test never released the gate"
        return super().ocr_frame(path, cfg)


def jobs_for(cfg, fakes, **kw):
    return Jobs(cfg, make_steps=fakes.steps, **kw)


def test_run_completes_and_logs(cfg):
    jobs = jobs_for(cfg, Fakes([1, 2]))
    jobs.start_run("cont", None)
    assert jobs.wait(5)
    st = jobs.state()
    assert not st.running and st.done == 2 and st.total == 2
    assert st.last.startswith("@cont: 2 done")
    assert jobs.tail(3)[0].startswith("[1/2]")


def test_start_while_running_is_busy(cfg):
    fakes = GatedFakes([1, 2])
    jobs = jobs_for(cfg, fakes)
    jobs.start_run("cont", None)
    assert fakes.entered.wait(5)
    with pytest.raises(Busy):
        jobs.start_run("cont", None)
    assert jobs.state().running and jobs.state().account == "cont"
    fakes.gate.set()
    assert jobs.wait(5)


def test_stop_ends_after_current_clip(cfg):
    fakes = GatedFakes([1, 2, 3])
    jobs = jobs_for(cfg, fakes)
    jobs.start_run("cont", None)
    assert fakes.entered.wait(5)
    assert jobs.stop() is True
    assert jobs.state().stopping
    fakes.gate.set()
    assert jobs.wait(5)
    st = jobs.state()
    assert not st.running and not st.stopping
    assert "stopped after 1/3" in st.last


def test_total_known_while_first_clip_runs(cfg):
    fakes = GatedFakes([1, 2, 3])
    jobs = jobs_for(cfg, fakes)
    jobs.start_run("cont", None)
    assert fakes.entered.wait(5)
    st = jobs.state()
    assert (st.done, st.total) == (0, 3)
    fakes.gate.set()
    jobs.wait(5)


def test_run_again_after_stop(cfg):
    fakes = GatedFakes([1, 2, 3])
    jobs = jobs_for(cfg, fakes)
    jobs.start_run("cont", None)
    assert fakes.entered.wait(5)
    jobs.stop()
    fakes.gate.set()
    jobs.wait(5)
    jobs.start_run("cont", None)
    jobs.wait(5)
    assert jobs.state().last.startswith("@cont: 2 done")


def test_stop_when_idle(cfg):
    assert Jobs(cfg).stop() is False


def test_run_error_logged_and_idle(cfg):
    fakes = Fakes([1])

    def broken(account, c):
        raise ListingError("blocked by TikTok")

    fakes.list_clips = broken
    jobs = jobs_for(cfg, fakes)
    jobs.start_run("cont", None)
    assert jobs.wait(5)
    assert jobs.state().last == "error: blocked by TikTok"
    assert not jobs.state().running


def test_log_since_returns_only_new_lines(cfg):
    jobs = jobs_for(cfg, Fakes([1, 2]))
    jobs.start_run("cont", None)
    jobs.wait(5)
    lines, seq = jobs.log_since(0)
    assert len(lines) == 5 and seq == 5
    assert lines[0] == "> run @cont"
    assert jobs.log_since(seq) == ([], 5)
    assert jobs.log_since(2) == (lines[2:], 5)


def test_log_capped(cfg):
    jobs = jobs_for(cfg, Fakes([1, 2, 3, 4, 5]), max_log=3)
    jobs.start_run("cont", None)
    jobs.wait(5)
    lines, seq = jobs.log_since(0)
    assert len(lines) == 3 and seq == 8
    assert jobs.tail(10) == lines


def test_new_run_marks_its_start_in_log(cfg):
    jobs = jobs_for(cfg, Fakes([1]))
    jobs.start_run("cont", 1)
    jobs.wait(5)
    assert any("run @cont (limit 1)" in l for l in jobs.tail(10))
