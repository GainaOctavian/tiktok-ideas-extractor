from datetime import date

from pipeline.report import export_lines, status_lines
from pipeline.state import ClipInfo, State


def seed(cfg, done=(), failed=()):
    with State(cfg.data_dir / "state.db") as s:
        s.add_listed("cont", [ClipInfo(i, f"u{i}", None, None) for i in [*done, *failed]])
        folder = cfg.data_dir / "transcripts" / "cont"
        folder.mkdir(parents=True, exist_ok=True)
        for i in done:
            (folder / f"{i}.txt").write_text(f"idea {i} is a long enough idea", encoding="utf-8")
            s.mark_done(i, 30)
        for i in failed:
            for _ in range(3):
                s.mark_failed(i, "boom")


def test_status_lines_match_cli_format(cfg):
    seed(cfg, done=["1"], failed=["2"])
    assert status_lines("cont", cfg) == [
        "@cont: 2 listed | 1 processed (0 low text) | 1 unexported | 0 exported | 1 failed (1 final) | 0 pending",
        "failed: 2 (3/3) boom",
        "1 clips failed 3 times and are skipped. Requeue them with: reset cont --failed",
    ]


def test_status_lines_show_skipped_photo_posts(cfg):
    seed(cfg, done=["1"])
    with State(cfg.data_dir / "state.db") as s:
        s.add_listed("cont", [ClipInfo("9", "u9", None, None)])
        s.mark_skipped("9", "photo post (no video)")
    assert status_lines("cont", cfg)[0].endswith("| 0 pending | 1 skipped (photo posts)")


def test_status_lines_unknown_account(cfg):
    assert "no clips yet" in status_lines("nobody", cfg)[0]


def test_export_lines(cfg):
    seed(cfg, done=["1"])
    lines = export_lines("cont", cfg, date(2026, 11, 22))
    assert lines[-1] == "1 clips exported"
    assert lines[0].endswith(".txt")
    assert export_lines("cont", cfg, date(2026, 11, 22)) == ["Nothing to export."]
