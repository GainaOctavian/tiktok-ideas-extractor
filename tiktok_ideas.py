"""TikTok Ideas Extractor CLI: run, export, status, reset."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from app.server import serve_ui
from pipeline.config import Config, load_config
from pipeline.frames import FfmpegMissing, require_ffmpeg
from pipeline.lister import ListingError, normalize_account
from pipeline.ocr import TesseractMissing, configure_tesseract
from pipeline.report import export_lines, reset_line, status_lines
from pipeline.runner import Steps, run_account

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yaml"

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

    ui = sub.add_parser("ui", help="open the local web page")
    ui.add_argument("--port", type=int, default=0, help="port on 127.0.0.1 (default: a free one)")
    ui.add_argument("--no-browser", action="store_true", help="don't open the browser")
    ui.add_argument("--ctl", action="store_true", help="let tiktok_ideas_ctl.py drive the app")
    return p


def cmd_status(account: str, cfg: Config) -> None:
    print("\n".join(status_lines(account, cfg)))


def cmd_export(account: str, cfg: Config) -> None:
    print("\n".join(export_lines(account, cfg, date.today())))


def cmd_reset(account: str, cfg: Config) -> None:
    print(reset_line(account, cfg))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "ui":
            serve_ui(load_config(args.config), args.port, not args.no_browser, args.ctl)
            return 0
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
