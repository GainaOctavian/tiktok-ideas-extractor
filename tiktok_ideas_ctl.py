"""tiktok-ideas-ctl: drive a running `tiktok_ideas.py ui --ctl` with command lines.

  python tiktok_ideas_ctl.py "run youraccount 5" wait status youraccount
  python tiktok_ideas_ctl.py -f script.txt
  "help" | python tiktok_ideas_ctl.py -

Exit codes: 0 ok, 1 stopped at an error, 2 no app listening (or usage).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pipeline.config import load_config

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yaml"
NOT_LISTENING = "no app listening; start it with: python tiktok_ideas.py ui --ctl"


def _script(args: argparse.Namespace) -> str:
    if args.file == "-":
        return sys.stdin.read()
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    return "\n".join(args.lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tiktok_ideas_ctl.py", description="Send command lines to the running UI.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("-f", "--file", help="read lines from a file, or - for stdin")
    p.add_argument("lines", nargs="*", help='command lines, e.g. "run youraccount 5" wait')
    args = p.parse_args(argv)
    if not args.lines and not args.file:
        print("usage: tiktok_ideas_ctl.py [--config PATH] (LINE ... | -f FILE | -f -); try: help", file=sys.stderr)
        return 2

    try:
        cfg = load_config(args.config)
        info = json.loads((cfg.data_dir / "ctl.json").read_text(encoding="utf-8"))
        script = _script(args)
    except FileNotFoundError:
        print(NOT_LISTENING, file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    req = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}/api/cmd", data=script.encode("utf-8"), headers={"X-Token": info["token"]}
    )
    try:
        # no timeout: `wait` blocks until the run ends
        with urllib.request.urlopen(req) as r:
            answer, code = r.read().decode("utf-8"), int(r.headers.get("X-Exit", "1"))
    except urllib.error.HTTPError as e:
        print(f"error: the app answered {e.code}: {e.read().decode('utf-8', 'replace')}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, ConnectionError):
        print(NOT_LISTENING, file=sys.stderr)
        return 2
    if answer:
        print(answer)
    return code


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
