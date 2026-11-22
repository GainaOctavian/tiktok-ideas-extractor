import dataclasses
from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline.lister import ListingError
from pipeline.runner import Steps, clear_work, run_account
from pipeline.state import ClipInfo, State


def clip(i):
    return ClipInfo(str(i), f"https://www.tiktok.com/@cont/video/{i}", None, None)


class Fakes:
    """Configurable fake pipeline steps that create real temp files like the real ones."""

    def __init__(self, ids, lines=None, fail_download=(), interrupt_ocr=()):
        self.ids = list(ids)
        self.lines = lines or {}
        self.fail_download = set(fail_download)
        self.interrupt_ocr = set(interrupt_ocr)
        self.downloaded = []

    def list_clips(self, account, cfg):
        return [clip(i) for i in self.ids]

    def download(self, url, dest_dir, cfg):
        clip_id = url.rsplit("/", 1)[-1]
        self.downloaded.append(clip_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "video.mp4").write_bytes(b"video")
        if clip_id in self.fail_download:
            raise RuntimeError(f"download failed for {clip_id}")
        return dest_dir / "video.mp4"

    def extract_frames(self, video, out_dir, cfg):
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for n in range(2):
            p = out_dir / f"{n:05d}.png"
            cv2.imwrite(str(p), np.zeros((10, 10, 3), np.uint8))
            paths.append(p)
        return paths

    def ocr_frame(self, path, cfg):
        clip_id = path.parent.parent.name
        if clip_id in self.interrupt_ocr:
            raise KeyboardInterrupt
        return self.lines.get(clip_id, [f"idea number {clip_id}", f"idea number {clip_id}"])

    def steps(self):
        return Steps(self.list_clips, self.download, self.extract_frames, self.ocr_frame)


def run(cfg, fakes, limit=None):
    out = []
    summary = run_account("cont", cfg, limit, fakes.steps(), out=out.append)
    return summary, out


def state(cfg):
    return State(cfg.data_dir / "state.db")


def media_files(root: Path):
    return [p for p in root.rglob("*") if p.suffix in {".mp4", ".png", ".webm"}]


def test_run_end_to_end_with_fakes(cfg, tmp_path):
    summary, out = run(cfg, Fakes([1, 2, 3]))
    assert (summary.listed_new, summary.processed, summary.done, summary.failed) == (3, 3, 3, 0)
    text = (cfg.data_dir / "transcripts" / "cont" / "2.txt").read_text(encoding="utf-8")
    assert text == "idea number 2"
    assert list(cfg.work_dir.iterdir()) == []
    assert media_files(tmp_path) == []
    assert out[0].startswith("[1/3] 3 done (")


def test_second_run_only_new(cfg):
    run(cfg, Fakes([1, 2, 3]))
    fakes = Fakes([1, 2, 3, 4])
    summary, _ = run(cfg, fakes)
    assert summary.processed == 1
    assert fakes.downloaded == ["4"]


def test_failed_clip_does_not_stop_run(cfg):
    summary, out = run(cfg, Fakes([1, 2, 3], fail_download=["2"]))
    assert (summary.done, summary.failed) == (2, 1)
    with state(cfg) as s:
        failed = s.failed("cont")
    assert [r.id for r in failed] == ["2"]
    assert "download failed for 2" in failed[0].error
    assert any("2 failed:" in line for line in out)


def test_failed_retried_then_final(cfg):
    for _ in range(3):
        run(cfg, Fakes([1], fail_download=["1"]))
    fakes = Fakes([1], fail_download=["1"])
    summary, out = run(cfg, fakes)
    assert fakes.downloaded == []
    assert summary.skipped_final == 1
    assert any("reset cont --failed" in line for line in out)
    with state(cfg) as s:
        assert s.failed("cont")[0].attempts == 3


@pytest.mark.parametrize("keep", [True, False])
def test_keep_failed_media(cfg, keep):
    cfg = dataclasses.replace(cfg, keep_failed_media=keep)
    run(cfg, Fakes([1], fail_download=["1"]))
    assert (cfg.work_dir / "1" / "video.mp4").exists() is keep


def test_interrupt_cleans_and_keeps_pending(cfg):
    with pytest.raises(KeyboardInterrupt):
        run(cfg, Fakes([1], interrupt_ocr=["1"]))
    assert not (cfg.work_dir / "1").exists()
    with state(cfg) as s:
        row = s.to_process("cont", 3)[0]
    assert (row.status, row.attempts) == ("pending", 0)

    leftover = cfg.work_dir / "999" / "video.mp4"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(b"x")
    run(cfg, Fakes([1]))
    assert list(cfg.work_dir.iterdir()) == []


def test_no_text_clip(cfg):
    summary, _ = run(cfg, Fakes([1], lines={"1": []}))
    assert summary.done == 1
    with state(cfg) as s:
        assert s.counts("cont", 3, 20).low_text == 1


def test_limit(cfg):
    fakes = Fakes([1, 2, 3, 4, 5])
    summary, _ = run(cfg, fakes, limit=2)
    assert summary.processed == 2
    assert fakes.downloaded == ["5", "4"]


def test_listing_error_writes_nothing(cfg):
    fakes = Fakes([1])

    def broken(account, cfg):
        raise ListingError("blocked")

    fakes.list_clips = broken
    with pytest.raises(ListingError):
        run(cfg, fakes)
    with state(cfg) as s:
        assert s.counts("cont", 3, 20).listed == 0


def test_clear_work_only_removes_clip_folders(tmp_path):
    # a mistaken work_dir (e.g. ".") must not wipe the repo, .git or the state
    (tmp_path / ".git").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "7301234567890").mkdir()
    (tmp_path / "7301234567890" / "video.mp4").write_bytes(b"v")
    clear_work(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [".git", "config.yaml", "data"]


def test_clear_work_refuses_dangerous_paths():
    with pytest.raises(ValueError):
        clear_work(Path.home())
    with pytest.raises(ValueError):
        clear_work(Path("C:/"))
