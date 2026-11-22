from datetime import date

from pipeline.exporter import TASK_LINE, build_export, write_export
from pipeline.state import ClipInfo, State

TODAY = date(2026, 11, 22)


def test_format_matches_spec():
    parts = build_export(
        "cont",
        [
            ("7301234567890", "add a daily login streak that gives a free pet\nlet players trade items in a lobby"),
            ("7301234567999", "add a pet shop"),
        ],
        TODAY,
        40000,
    )
    assert len(parts) == 1
    assert parts[0].splitlines() == [
        "TASK: Extract only the Roblox game-making suggestions. One bullet each, followed by [id]. No commentary.",
        "# @cont | 2 clips | 2026-11-22",
        "[7301234567890]",
        "add a daily login streak that gives a free pet",
        "let players trade items in a lobby",
        "[7301234567999]",
        "add a pet shop",
    ]
    assert "http" not in parts[0]


def test_empty_transcript_skipped():
    parts = build_export("cont", [("1", "a pet idea"), ("2", "  \n")], TODAY, 40000)
    assert "# @cont | 1 clips | 2026-11-22" in parts[0]
    assert "[2]" not in parts[0]


def test_nothing_with_text_gives_no_parts():
    assert build_export("cont", [("1", "")], TODAY, 40000) == []


def test_split_at_clip_boundaries():
    clips = [(str(i), ("word " * 200).strip()) for i in range(10)]
    parts = build_export("cont", clips, TODAY, 3000)
    assert len(parts) > 1
    seen = []
    for i, part in enumerate(parts, 1):
        assert len(part) <= 3000
        lines = part.splitlines()
        assert lines[0] == TASK_LINE
        assert lines[1].endswith(f"| part {i}/{len(parts)}")
        seen += [l[1:-1] for l in lines if l.startswith("[")]
    assert sorted(seen, key=int) == [str(i) for i in range(10)]


def test_oversized_single_clip_gets_own_part():
    big = ("idea " * 1000).strip()
    parts = build_export("cont", [("1", "small idea"), ("2", big), ("3", "other idea")], TODAY, 3000)
    assert len(parts) == 3
    assert big in parts[1]


def seed(cfg, texts, exported=()):
    with State(cfg.data_dir / "state.db") as s:
        s.add_listed("cont", [ClipInfo(i, f"u{i}", None, None) for i in texts])
        folder = cfg.data_dir / "transcripts" / "cont"
        folder.mkdir(parents=True, exist_ok=True)
        for i, text in texts.items():
            (folder / f"{i}.txt").write_text(text, encoding="utf-8")
            s.mark_done(i, len(text))
        s.mark_exported(exported)


def test_write_export_marks_only_unexported(cfg):
    seed(cfg, {"1": "idea one", "2": "idea two", "3": "idea three", "4": "old idea"}, exported=["4"])
    with State(cfg.data_dir / "state.db") as s:
        paths, n = write_export("cont", cfg, s, TODAY)
        assert n == 3
        text = "".join(p.read_text(encoding="utf-8") for p in paths)
        assert all(f"[{i}]" in text for i in "123") and "[4]" not in text
        assert all(p.parent == cfg.data_dir / "exports" for p in paths)
        assert s.unexported("cont") == []
        assert write_export("cont", cfg, s, TODAY) == ([], 0)


def test_write_export_marks_empty_clips_exported(cfg):
    seed(cfg, {"1": "", "2": "idea"})
    with State(cfg.data_dir / "state.db") as s:
        paths, n = write_export("cont", cfg, s, TODAY)
        assert n == 2 and len(paths) == 1
        assert s.unexported("cont") == []


def test_write_export_only_empty_clips_writes_no_file(cfg):
    seed(cfg, {"1": ""})
    with State(cfg.data_dir / "state.db") as s:
        assert write_export("cont", cfg, s, TODAY) == ([], 1)
        assert s.unexported("cont") == []


def test_write_export_utf8(cfg):
    seed(cfg, {"1": "café “quotes” 🎮"})
    with State(cfg.data_dir / "state.db") as s:
        paths, _ = write_export("cont", cfg, s, TODAY)
        assert "café “quotes” 🎮" in paths[0].read_text(encoding="utf-8")
