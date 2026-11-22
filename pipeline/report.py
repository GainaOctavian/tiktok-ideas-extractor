"""Text answers shared by the CLI, the UI and the ctl."""
from __future__ import annotations

from datetime import date

from pipeline.config import Config
from pipeline.exporter import write_export
from pipeline.runner import final_hint
from pipeline.state import State

MAX_LISTED_IDS = 20


def _ids(rows) -> str:
    ids = [r.id for r in rows]
    more = len(ids) - MAX_LISTED_IDS
    return ", ".join(ids[:MAX_LISTED_IDS]) + (f" and {more} more" if more > 0 else "")


def status_lines(account: str, cfg: Config) -> list[str]:
    with State(cfg.data_dir / "state.db") as state:
        c = state.counts(account, cfg.max_attempts, cfg.low_text_chars)
        if c.listed == 0:
            return [f"@{account}: no clips yet. Run: python tiktok_ideas.py run {account}"]
        lines = [
            f"@{account}: {c.listed} listed | {c.done + c.exported} processed ({c.low_text} low text) | "
            f"{c.done} unexported | {c.exported} exported | "
            f"{c.failed} failed ({c.failed_final} final) | {c.pending} pending"
        ]
        lines += [f"failed: {r.id} ({r.attempts}/{cfg.max_attempts}) {r.error}" for r in state.failed(account)]
        if c.failed_final:
            lines.append(final_hint(account, c.failed_final, cfg.max_attempts))
        low = state.low_text(account, cfg.low_text_chars)
        if low:
            lines.append(f"low text: {_ids(low)}")
        return lines


def reset_line(account: str, cfg: Config) -> str:
    with State(cfg.data_dir / "state.db") as state:
        return f"{state.reset_failed(account)} failed clips requeued"


def export_lines(account: str, cfg: Config, today: date) -> list[str]:
    with State(cfg.data_dir / "state.db") as state:
        paths, count = write_export(account, cfg, state, today)
    if count == 0:
        return ["Nothing to export."]
    lines = [str(p) for p in paths]
    if not paths:
        lines.append("No transcript had text.")
    lines.append(f"{count} clips exported")
    return lines
