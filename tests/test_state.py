import pytest

from pipeline.state import ClipInfo, State


def clip(i):
    return ClipInfo(id=str(i), url=f"https://www.tiktok.com/@a/video/{i}", title=None, published=None)


@pytest.fixture
def state(tmp_path):
    with State(tmp_path / "db" / "state.db") as s:
        yield s


def ids(rows):
    return [r.id for r in rows]


def test_add_listed_counts_only_new(state):
    assert state.add_listed("a", [clip(1), clip(2)]) == 2
    assert state.add_listed("a", [clip(1), clip(2), clip(3)]) == 1


def test_to_process_skips_done_and_orders_newest_first(state):
    state.add_listed("a", [clip(100), clip(300), clip(200)])
    state.mark_done("200", 10)
    assert ids(state.to_process("a", 3)) == ["300", "100"]


def test_failed_retried_until_max_attempts(state):
    state.add_listed("a", [clip(1)])
    for attempt in (1, 2):
        state.mark_failed("1", "boom")
        assert ids(state.to_process("a", 3)) == ["1"], attempt
    state.mark_failed("1", "boom")
    assert state.to_process("a", 3) == []
    assert state.counts("a", 3, 20).failed_final == 1


def test_mark_failed_truncates_error(state):
    state.add_listed("a", [clip(1)])
    state.mark_failed("1", "x" * 2000)
    assert len(state.failed("a")[0].error) == 500


def test_reset_failed_requeues(state):
    state.add_listed("a", [clip(1)])
    for _ in range(3):
        state.mark_failed("1", "boom")
    assert state.reset_failed("a") == 1
    row = state.to_process("a", 3)[0]
    assert (row.status, row.attempts, row.error) == ("pending", 0, None)


def test_export_flow(state):
    state.add_listed("a", [clip(1), clip(2)])
    state.mark_done("1", 10)
    state.mark_done("2", 10)
    state.mark_exported(["1"])
    assert ids(state.unexported("a")) == ["2"]
    assert state.counts("a", 3, 20).exported == 1


def test_low_text(state):
    state.add_listed("a", [clip(1), clip(2)])
    state.mark_done("1", 5)
    state.mark_done("2", 300)
    assert ids(state.low_text("a", 20)) == ["1"]
    assert state.counts("a", 3, 20).low_text == 1


def test_counts(state):
    state.add_listed("a", [clip(1), clip(2), clip(3), clip(4)])
    state.mark_done("1", 50)
    state.mark_done("2", 50)
    state.mark_exported(["2"])
    state.mark_failed("3", "boom")
    c = state.counts("a", 3, 20)
    assert (c.listed, c.pending, c.done, c.failed, c.failed_final, c.exported) == (4, 1, 1, 1, 0, 1)


def test_accounts_are_isolated(state):
    state.add_listed("a", [clip(1)])
    state.add_listed("b", [clip(2)])
    assert ids(state.to_process("b", 3)) == ["2"]
    assert state.counts("b", 3, 20).listed == 1
