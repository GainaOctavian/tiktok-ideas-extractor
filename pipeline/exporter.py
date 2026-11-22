"""Token-lean export of unexported transcripts, to paste into Claude."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from pipeline.config import Config
from pipeline.state import State

TASK_LINE = (
    "TASK: Extract only the Roblox game-making suggestions. "
    "One bullet each, followed by [id]. No commentary."
)


def _header(account: str, n: int, today: date, part: str = "") -> str:
    return f"# @{account} | {n} clips | {today.isoformat()}{part}"


def build_export(account: str, clips: list[tuple[str, str]], today: date, max_chars: int) -> list[str]:
    """Render export parts; clips without text are left out, splits fall between clips."""
    blocks: list[str] = []
    for clip_id, text in clips:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            blocks.append("\n".join([f"[{clip_id}]", *lines]) + "\n")
    if not blocks:
        return []

    # Budget for the worst-case header so the part suffix can't push a part over max_chars.
    overhead = len(TASK_LINE) + 1 + len(_header(account, len(blocks), today, " | part 9999/9999")) + 1
    groups: list[list[str]] = [[]]
    size = overhead
    for block in blocks:
        if groups[-1] and size + len(block) > max_chars:
            groups.append([])
            size = overhead
        groups[-1].append(block)
        size += len(block)

    total = len(groups)
    parts = []
    for i, group in enumerate(groups, 1):
        suffix = f" | part {i}/{total}" if total > 1 else ""
        parts.append(f"{TASK_LINE}\n{_header(account, len(group), today, suffix)}\n" + "".join(group))
    return parts


def write_export(account: str, cfg: Config, state: State, today: date) -> tuple[list[Path], int]:
    """Write unexported transcripts to data/exports and mark them exported."""
    rows = state.unexported(account)
    if not rows:
        return [], 0

    folder = cfg.data_dir / "transcripts" / account
    clips = []
    for row in rows:
        path = folder / f"{row.id}.txt"
        clips.append((row.id, path.read_text(encoding="utf-8") if path.exists() else ""))

    parts = build_export(account, clips, today, cfg.export_max_chars)
    out_dir = cfg.data_dir / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{account}-{today.isoformat()}-{datetime.now().strftime('%H%M%S')}"
    paths = []
    for i, part in enumerate(parts, 1):
        name = f"{stamp}-{i}.txt" if len(parts) > 1 else f"{stamp}.txt"
        path = out_dir / name
        path.write_text(part, encoding="utf-8", newline="\n")
        paths.append(path)

    state.mark_exported(r.id for r in rows)
    return paths, len(rows)
