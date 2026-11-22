"""Run the per-clip pipeline for one account."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pipeline import downloader, frames, lister, ocr
from pipeline.cleaner import clean_lines
from pipeline.config import Config
from pipeline.state import ClipRow, State


@dataclass
class Steps:
    list_clips: Callable = lister.list_clips
    download: Callable = downloader.download
    extract_frames: Callable = frames.extract_frames
    ocr_frame: Callable = ocr.ocr_frame


@dataclass
class RunSummary:
    listed_new: int
    processed: int
    done: int
    failed: int
    skipped_final: int
    skipped: int = 0  # photo posts


def clear_work(work_dir: Path) -> None:
    """Remove clip folders (work/<numeric id>/) left by an interrupted run.

    Only numeric folders are touched, so a mistaken work_dir can't wipe unrelated files.
    """
    work_dir = Path(work_dir).resolve()
    if work_dir.parent == work_dir or work_dir == Path.home().resolve():
        raise ValueError(f"Refusing to use {work_dir} as work_dir; set it to a dedicated folder")
    work_dir.mkdir(parents=True, exist_ok=True)
    for child in work_dir.iterdir():
        if child.name.isdigit() and child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)


def transcript_path(cfg: Config, account: str, clip_id: str) -> Path:
    return cfg.data_dir / "transcripts" / account / f"{clip_id}.txt"


def process_clip(clip: ClipRow, cfg: Config, state: State, steps: Steps) -> tuple[str, str]:
    """Returns (outcome, message); outcome is done, failed or skipped."""
    work = cfg.work_dir / clip.id
    failed = False
    try:
        video = steps.download(clip.url, work, cfg)
        lines: list[str] = []
        for frame in steps.extract_frames(video, work / "frames", cfg):
            lines.extend(steps.ocr_frame(frame, cfg))
        text = "\n".join(clean_lines(lines, cfg.dedupe_similarity))

        out = transcript_path(cfg, clip.account, clip.id)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        state.mark_done(clip.id, len(text))
        return "done", f"done ({len(text)} chars)"
    except downloader.PhotoPost as e:
        state.mark_skipped(clip.id, str(e))
        return "skipped", f"skipped: {e}"
    except Exception as e:
        failed = True
        message = f"{type(e).__name__}: {e}"
        state.mark_failed(clip.id, message)
        return "failed", f"failed: {message}"
    finally:
        if not (failed and cfg.keep_failed_media):
            shutil.rmtree(work, ignore_errors=True)


def run_account(
    account: str,
    cfg: Config,
    limit: int | None,
    steps: Steps | None = None,
    out: Callable = print,
    should_stop: Callable[[], bool] | None = None,
) -> RunSummary:
    """Process the account's queue; should_stop is checked before each clip (cooperative stop)."""
    steps = steps or Steps()
    clear_work(cfg.work_dir)
    clips = steps.list_clips(account, cfg)

    with State(cfg.data_dir / "state.db") as state:
        listed_new = state.add_listed(account, clips)
        queue = state.to_process(account, cfg.max_attempts)
        if limit is not None:
            queue = queue[:limit]
        skipped_final = state.counts(account, cfg.max_attempts, cfg.low_text_chars).failed_final

        done = failed = skipped = processed = 0
        stopped = False
        if queue:
            out(f"queue: {len(queue)} clips")  # lets the UI show progress before the first clip ends
        for i, clip in enumerate(queue, 1):
            if should_stop and should_stop():
                stopped = True
                break
            outcome, message = process_clip(clip, cfg, state, steps)
            processed += 1
            done += outcome == "done"
            failed += outcome == "failed"
            skipped += outcome == "skipped"
            out(f"[{i}/{len(queue)}] {clip.id} {message}")

    summary = RunSummary(listed_new, processed, done, failed, skipped_final, skipped)
    photos = f", {skipped} photo posts skipped" if skipped else ""
    if stopped:
        out(f"@{account}: stopped after {processed}/{len(queue)} clips ({done} done, {failed} failed{photos}).")
    elif not queue:
        out(f"@{account}: nothing new to process ({listed_new} new clips listed).")
    else:
        out(f"@{account}: {done} done, {failed} failed{photos}, {listed_new} new clips listed.")
    if skipped_final:
        out(final_hint(account, skipped_final, cfg.max_attempts))
    return summary


def final_hint(account: str, count: int, max_attempts: int) -> str:
    return (
        f"{count} clips failed {max_attempts} times and are skipped. "
        f"Requeue them with: reset {account} --failed"
    )
