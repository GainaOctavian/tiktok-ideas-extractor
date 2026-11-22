"""Line-based command language shared by the web UI and the ctl.

One command per line, '#' comments, "quotes" for spaces. Answers are compact
text; a script stops at the first error: `error at line N (<line>): <reason>`.
"""
from __future__ import annotations

import shlex
from datetime import date
from typing import Callable

from app.jobs import Busy, Jobs
from pipeline.config import Config
from pipeline.lister import normalize_account
from pipeline.report import export_lines, reset_line, status_lines


class CommandError(Exception):
    pass


# name -> (usage, help)
COMMANDS: dict[str, tuple[str, str]] = {
    "run": ("run <account> [limit]", "process new clips of an account in the background"),
    "stop": ("stop", "stop the run after the current clip"),
    "wait": ("wait", "wait until the run ends; prints its last line"),
    "state": ("state", "idle, or the running account and progress"),
    "log": ("log [n]", "last n log lines (default 20)"),
    "status": ("status <account>", "clip counts, failures, low-text clips"),
    "export": ("export <account>", "write unexported transcripts for Claude"),
    "reset": ("reset <account>", "requeue failed clips (not during a run)"),
    "exports": ("exports", "export files, newest first"),
    "help": ("help", "this list"),
}


def parse_line(line: str) -> list[str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    try:
        words = shlex.split(line)
    except ValueError as e:
        raise CommandError(f"cannot parse: {e}") from e
    words[0] = words[0].lower()
    return words


def _account(args: list[str], max_args: int) -> str:
    if not args:
        raise CommandError("missing account")
    if len(args) > max_args:
        raise CommandError("too many arguments")
    try:
        return normalize_account(args[0])
    except ValueError as e:
        raise CommandError(str(e)) from e


def _no_args(args: list[str]) -> None:
    if args:
        raise CommandError("too many arguments")


def _positive_int(text: str, what: str) -> int:
    if not text.isdigit() or int(text) < 1:
        raise CommandError(f"{what} must be a whole number of at least 1")
    return int(text)


def _cmd_run(args, cfg, jobs):
    account = _account(args, 2)
    limit = _positive_int(args[1], "limit") if len(args) > 1 else None
    try:
        jobs.start_run(account, limit)
    except Busy as e:
        raise CommandError(str(e)) from e
    return [f"started @{account}" + (f" (limit {limit})" if limit else "")]


def _cmd_stop(args, cfg, jobs):
    _no_args(args)
    return ["stopping after the current clip" if jobs.stop() else "nothing running"]


def _cmd_wait(args, cfg, jobs):
    _no_args(args)
    if jobs.state().account is None:
        return ["nothing running"]
    jobs.wait()
    return [jobs.state().last or "idle"]


def _cmd_state(args, cfg, jobs):
    _no_args(args)
    st = jobs.state()
    if st.running:
        progress = f" {st.done}/{st.total}" if st.total else " listing clips"
        lines = [f"running @{st.account}{progress}" + (" (stopping)" if st.stopping else "")]
    else:
        lines = ["idle"]
        if st.last:
            lines.append(f"last: {st.last}")
    return lines


def _cmd_log(args, cfg, jobs):
    if len(args) > 1:
        raise CommandError("too many arguments")
    n = _positive_int(args[0], "n") if args else 20
    return jobs.tail(n) or ["(log is empty)"]


def _cmd_status(args, cfg, jobs):
    return status_lines(_account(args, 1), cfg)


def _cmd_export(args, cfg, jobs):
    return export_lines(_account(args, 1), cfg, date.today())


def _cmd_reset(args, cfg, jobs):
    account = _account(args, 1)
    if jobs.state().running:
        raise CommandError("stop the run first")
    return [reset_line(account, cfg)]


def _cmd_exports(args, cfg, jobs):
    _no_args(args)
    folder = cfg.data_dir / "exports"
    files = sorted(folder.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
    return [f"{p.name}  {p.stat().st_size / 1024:.1f} KB" for p in files] or ["no exports"]


def _cmd_help(args, cfg, jobs):
    width = max(len(usage) for usage, _ in COMMANDS.values())
    return [f"{usage.ljust(width)}  {text}" for usage, text in COMMANDS.values()]


_HANDLERS: dict[str, Callable[[list[str], Config, Jobs], list[str]]] = {
    "run": _cmd_run,
    "stop": _cmd_stop,
    "wait": _cmd_wait,
    "state": _cmd_state,
    "log": _cmd_log,
    "status": _cmd_status,
    "export": _cmd_export,
    "reset": _cmd_reset,
    "exports": _cmd_exports,
    "help": _cmd_help,
}


def run_script(text: str, cfg: Config, jobs: Jobs) -> tuple[str, int]:
    """Run lines in order; returns (answer text, exit code 0 ok / 1 stopped at an error)."""
    out: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        try:
            words = parse_line(line)
            if words is None:
                continue
            handler = _HANDLERS.get(words[0])
            if handler is None:
                raise CommandError(f"unknown command '{words[0]}' (try: help)")
            out.extend(handler(words[1:], cfg, jobs))
        except CommandError as e:
            out.append(f"error at line {number} ({line.strip()}): {e}")
            return "\n".join(out), 1
        except Exception as e:  # unexpected failure in a command: report like any error
            out.append(f"error at line {number} ({line.strip()}): {type(e).__name__}: {e}")
            return "\n".join(out), 1
    return "\n".join(out), 0
