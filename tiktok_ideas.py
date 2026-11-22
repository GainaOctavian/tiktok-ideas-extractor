"""TikTok Ideas Extractor CLI: run, export, status, reset."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from pipeline.config import Config, load_config
from pipeline.exporter import write_export
from pipeline.frames import FfmpegMissing, require_ffmpeg
from pipeline.lister import ListingError, normalize_account
from pipeline.ocr import TesseractMissing, configure_tesseract
from pipeline.runner import Steps, final_hint, run_account
from pipeline.state import State

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yaml"
MAX_LISTED_IDS = 20

make_steps = Steps  # replaced in tests


class UsageError(Exception):
    pass


def preflight(cfg: Config) -> None:
    require_ffmpeg()
    configure_tesseract(cfg)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tiktok_ideas.py", description=__doc__)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="path to config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="process every new clip of an account")
    run.add_argument("account", nargs="?", default="")
    run.add_argument("--limit", type=int, help="process at most N new clips")

    for name, text in (("export", "write unexported transcripts for Claude"), ("status", "show clip counts")):
        sub.add_parser(name, help=text).add_argument("account", nargs="?", default="")

    reset = sub.add_parser("reset", help="requeue clips")
    reset.add_argument("account", nargs="?", default="")
    reset.add_argument("--failed", action="store_true", required=True, help="requeue failed clips")
    return p


def _ids(rows) -> str:
    ids = [r.id for r in rows]
    more = len(ids) - MAX_LISTED_IDS
    return ", ".join(ids[:MAX_LISTED_IDS]) + (f" and {more} more" if more > 0 else "")


def cmd_status(account: str, cfg: Config) -> None:
    with State(cfg.data_dir / "state.db") as state:
        c = state.counts(account, cfg.max_attempts, cfg.low_text_chars)
        if c.listed == 0:
            print(f"@{account}: no clips yet. Run: python tiktok_ideas.py run @{account}")
            return
        print(
            f"@{account}: {c.listed} listed | {c.done + c.exported} processed ({c.low_text} low text) | "
            f"{c.done} unexported | {c.exported} exported | "
            f"{c.failed} failed ({c.failed_final} final) | {c.pending} pending"
        )
        for row in state.failed(account):
            print(f"failed: {row.id} ({row.attempts}/{cfg.max_attempts}) {row.error}")
        if c.failed_final:
            print(final_hint(account, c.failed_final, cfg.max_attempts))
        low = state.low_text(account, cfg.low_text_chars)
        if low:
            print(f"low text: {_ids(low)}")


def cmd_export(account: str, cfg: Config) -> None:
    with State(cfg.data_dir / "state.db") as state:
        paths, count = write_export(account, cfg, state, date.today())
    if count == 0:
        print("Nothing to export.")
        return
    for path in paths:
        print(path)
    if not paths:
        print("No transcript had text.")
    print(f"{count} clips exported")


def cmd_reset(account: str, cfg: Config) -> None:
    with State(cfg.data_dir / "state.db") as state:
        print(f"{state.reset_failed(account)} failed clips requeued")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not args.account.strip():
            raise UsageError(
                "missing account. In PowerShell an unquoted @name is dropped: "
                "write the account without @ (name) or in quotes ('@name')."
            )
        cfg = load_config(args.config)
        try:
            account = normalize_account(args.account)
        except ValueError as e:
            raise UsageError(str(e)) from e

        if args.command == "run":
            if args.limit is not None and args.limit < 1:
                raise UsageError("--limit must be at least 1")
            preflight(cfg)
            run_account(account, cfg, args.limit, make_steps())
        elif args.command == "export":
            cmd_export(account, cfg)
        elif args.command == "status":
            cmd_status(account, cfg)
        elif args.command == "reset":
            cmd_reset(account, cfg)
        return 0
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (ListingError, FfmpegMissing, TesseractMissing, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. The current clip stays queued; work/ is emptied on the next run.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
