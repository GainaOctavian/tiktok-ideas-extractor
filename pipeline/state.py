"""SQLite state: one row per clip (steps 2 and 7)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ClipInfo:
    id: str
    url: str
    title: str | None
    published: str | None  # YYYY-MM-DD


@dataclass(frozen=True)
class ClipRow:
    id: str
    account: str
    url: str
    title: str | None
    published: str | None
    status: str
    error: str | None
    attempts: int
    chars: int | None


@dataclass(frozen=True)
class StatusCounts:
    listed: int
    pending: int
    done: int
    failed: int
    failed_final: int
    exported: int
    low_text: int


_SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    published TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending','done','failed','exported')),
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    chars INTEGER,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS clips_account_status ON clips(account, status);
"""

_COLUMNS = "id, account, url, title, published, status, error, attempts, chars"
_NEWEST_FIRST = "ORDER BY CAST(id AS INTEGER) DESC"
_MAX_ERROR = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State:
    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path)
        self._db.executescript(_SCHEMA)

    def __enter__(self) -> "State":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._db.close()

    def _rows(self, where: str, params: tuple) -> list[ClipRow]:
        cur = self._db.execute(f"SELECT {_COLUMNS} FROM clips WHERE {where} {_NEWEST_FIRST}", params)
        return [ClipRow(*r) for r in cur.fetchall()]

    def add_listed(self, account: str, clips: Iterable[ClipInfo]) -> int:
        with self._db:
            before = self._db.total_changes
            self._db.executemany(
                "INSERT OR IGNORE INTO clips (id, account, url, title, published, status, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                [(c.id, account, c.url, c.title, c.published, _now()) for c in clips],
            )
            return self._db.total_changes - before

    def to_process(self, account: str, max_attempts: int) -> list[ClipRow]:
        return self._rows(
            "account = ? AND (status = 'pending' OR (status = 'failed' AND attempts < ?))",
            (account, max_attempts),
        )

    def mark_done(self, clip_id: str, chars: int) -> None:
        with self._db:
            self._db.execute(
                "UPDATE clips SET status = 'done', error = NULL, chars = ?, updated_at = ? WHERE id = ?",
                (chars, _now(), clip_id),
            )

    def mark_failed(self, clip_id: str, error: str) -> None:
        with self._db:
            self._db.execute(
                "UPDATE clips SET status = 'failed', attempts = attempts + 1, error = ?, updated_at = ? "
                "WHERE id = ?",
                (error[:_MAX_ERROR], _now(), clip_id),
            )

    def unexported(self, account: str) -> list[ClipRow]:
        return self._rows("account = ? AND status = 'done'", (account,))

    def mark_exported(self, clip_ids: Iterable[str]) -> None:
        with self._db:
            self._db.executemany(
                "UPDATE clips SET status = 'exported', updated_at = ? WHERE id = ? AND status = 'done'",
                [(_now(), i) for i in clip_ids],
            )

    def reset_failed(self, account: str) -> int:
        with self._db:
            cur = self._db.execute(
                "UPDATE clips SET status = 'pending', attempts = 0, error = NULL, updated_at = ? "
                "WHERE account = ? AND status = 'failed'",
                (_now(), account),
            )
            return cur.rowcount

    def failed(self, account: str) -> list[ClipRow]:
        return self._rows("account = ? AND status = 'failed'", (account,))

    def low_text(self, account: str, low_text_chars: int) -> list[ClipRow]:
        return self._rows(
            "account = ? AND status IN ('done', 'exported') AND chars < ?", (account, low_text_chars)
        )

    def counts(self, account: str, max_attempts: int, low_text_chars: int) -> StatusCounts:
        row = self._db.execute(
            """SELECT COUNT(*),
                      SUM(status = 'pending'),
                      SUM(status = 'done'),
                      SUM(status = 'failed'),
                      SUM(status = 'failed' AND attempts >= ?),
                      SUM(status = 'exported'),
                      SUM(status IN ('done', 'exported') AND chars < ?)
               FROM clips WHERE account = ?""",
            (max_attempts, low_text_chars, account),
        ).fetchone()
        return StatusCounts(*(v or 0 for v in row))
