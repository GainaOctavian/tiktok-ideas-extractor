"""Background runs for the UI: one at a time, cooperative stop, in-memory log."""
from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable

from pipeline.config import Config
from pipeline.runner import Steps, run_account

_PROGRESS = re.compile(r"^\[(\d+)/(\d+)\]")
_QUEUE = re.compile(r"^queue: (\d+) clips$")


class Busy(Exception):
    pass


@dataclass(frozen=True)
class JobState:
    running: bool
    account: str | None
    done: int
    total: int
    stopping: bool
    last: str | None


class Jobs:
    def __init__(
        self,
        cfg: Config,
        make_steps: Callable[[], Steps] = Steps,
        max_log: int = 500,
        preflight: Callable[[Config], None] | None = None,
    ):
        self.cfg = cfg
        self._make_steps = make_steps
        self._preflight = preflight
        self._lock = threading.Lock()
        self._log: deque[str] = deque(maxlen=max_log)
        self._seq = 0  # number of lines ever logged
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._account: str | None = None
        self._done = self._total = 0
        self._last: str | None = None

    # -- log -----------------------------------------------------------------
    def _append(self, line: str) -> None:
        with self._lock:
            self._append_locked(line)

    def _append_locked(self, line: str) -> None:
        self._log.append(line)
        self._seq += 1
        m = _PROGRESS.match(line)
        if m:
            self._done, self._total = int(m.group(1)), int(m.group(2))
        q = _QUEUE.match(line)
        if q:
            self._done, self._total = 0, int(q.group(1))

    def log_since(self, seq: int) -> tuple[list[str], int]:
        """Lines logged after the first `seq` lines (only those still in the buffer)."""
        with self._lock:
            first = self._seq - len(self._log)  # seq number of the oldest kept line
            start = max(seq, first) - first
            return list(self._log)[start:], self._seq

    def tail(self, n: int) -> list[str]:
        with self._lock:
            return list(self._log)[-n:] if n > 0 else []

    # -- runs ----------------------------------------------------------------
    def _running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_run(self, account: str, limit: int | None) -> None:
        with self._lock:
            if self._running():
                raise Busy(f"a run is already active (@{self._account})")
            self._stop.clear()
            self._account = account
            self._done = self._total = 0
            self._last = None
            self._append_locked(f"> run @{account}" + (f" (limit {limit})" if limit else ""))
            # started under the lock so a concurrent start_run sees it alive
            self._thread = threading.Thread(target=self._run, args=(account, limit), daemon=True)
            self._thread.start()

    def _run(self, account: str, limit: int | None) -> None:
        try:
            if self._preflight:
                self._preflight(self.cfg)
            run_account(account, self.cfg, limit, self._make_steps(), out=self._append, should_stop=self._stop.is_set)
        except Exception as e:  # report and go idle; the UI shows it
            self._append(f"error: {e}")
        with self._lock:
            self._last = self._log[-1] if self._log else None

    def stop(self) -> bool:
        if not self._running():
            return False
        self._stop.set()
        return True

    def wait(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return not self._running()

    def state(self) -> JobState:
        with self._lock:
            running = self._running()
            return JobState(
                running=running,
                account=self._account,
                done=self._done,
                total=self._total,
                stopping=running and self._stop.is_set(),
                last=self._last,
            )
