"""Local HTTP server for the UI and the ctl (127.0.0.1 only, token on every request)."""
from __future__ import annotations

import hmac
import json
import os
import secrets
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app.commands import run_script
from app.jobs import Jobs
from pipeline.config import Config
from pipeline.frames import require_ffmpeg
from pipeline.ocr import configure_tesseract

STATIC = Path(__file__).resolve().parent / "static"
CTL_ENV = "TIKTOK_IDEAS_CTL"
MAX_BODY = 64 * 1024


def preflight(cfg: Config) -> None:
    require_ffmpeg()
    configure_tesseract(cfg)


def ctl_file(cfg: Config) -> Path:
    return cfg.data_dir / "ctl.json"


def make_server(
    cfg: Config, port: int = 0, token: str | None = None, jobs: Jobs | None = None
) -> tuple[ThreadingHTTPServer, str]:
    token = token or secrets.token_urlsafe(24)
    jobs = jobs or Jobs(cfg, preflight=preflight)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the console for the app's own messages
            pass

        def _authorized(self, query: dict) -> bool:
            given = self.headers.get("X-Token") or (query.get("t") or [""])[0]
            return hmac.compare_digest(given.encode(), token.encode())

        def _send(self, status: int, body: str, content_type: str = "text/plain", headers: dict | None = None):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _read_body(self) -> bytes | None:
            """Read the whole body first: replying before reading it can reset the connection on Windows."""
            raw = self.headers.get("Content-Length") or "0"
            if not raw.isdigit():
                self._send(400, "bad Content-Length")
                return None
            length = int(raw)
            if length > MAX_BODY:
                remaining = min(length, 16 * MAX_BODY)  # drain (bounded) so the client gets the answer
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self.close_connection = True
                self._send(413, f"script too long (max {MAX_BODY // 1024} KB)")
                return None
            return self.rfile.read(length)

        def _route(self, method: str) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            body = self._read_body() if method == "POST" else b""
            if body is None:
                return
            if not self._authorized(query):
                return self._send(403, "forbidden: missing or wrong token")

            if method == "GET" and url.path == "/":
                return self._send(200, (STATIC / "index.html").read_text(encoding="utf-8"), "text/html")
            if method == "POST" and url.path == "/api/cmd":
                script = body.decode("utf-8", errors="replace")
                answer, code = run_script(script, cfg, jobs)
                return self._send(200, answer, headers={"X-Exit": str(code)})
            if method == "GET" and url.path == "/api/poll":
                raw_since = (query.get("since") or ["0"])[0]
                since = int(raw_since) if raw_since.isdigit() else 0
                lines, nxt = jobs.log_since(since)
                body = json.dumps({"state": asdict(jobs.state()), "log": lines, "next": nxt})
                return self._send(200, body, "application/json")
            if method == "GET" and url.path.startswith("/api/export/"):
                return self._send_export(unquote(url.path[len("/api/export/"):]))
            return self._send(404, "not found")

        def _send_export(self, name: str) -> None:
            folder = (cfg.data_dir / "exports").resolve()
            path = (folder / name).resolve()
            if Path(name).name != name or not name.endswith(".txt") or path.parent != folder or not path.is_file():
                return self._send(404, "not found")
            return self._send(200, path.read_text(encoding="utf-8"))

        def do_GET(self) -> None:
            self._route("GET")

        def do_POST(self) -> None:
            self._route("POST")

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.jobs = jobs  # type: ignore[attr-defined]
    return httpd, token


def serve_ui(cfg: Config, port: int, open_browser: bool, ctl: bool, jobs: Jobs | None = None) -> None:
    httpd, token = make_server(cfg, port, jobs=jobs)
    actual_port = httpd.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/?t={token}"
    ctl = ctl or os.environ.get(CTL_ENV) == "1"
    info = ctl_file(cfg)
    if ctl:
        info.parent.mkdir(parents=True, exist_ok=True)
        info.write_text(json.dumps({"port": actual_port, "token": token}), encoding="utf-8")

    print(f"TikTok Ideas UI: {url}", flush=True)
    print("Keep this window open while you use the page. Ctrl+C to quit.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        running = httpd.jobs  # type: ignore[attr-defined]
        if running.stop():
            print("Stopping the run after the current clip...")
            running.wait(120)
        httpd.server_close()
        if ctl:
            info.unlink(missing_ok=True)
