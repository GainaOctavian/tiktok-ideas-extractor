import json
import threading
import urllib.error
import urllib.request

import pytest

from app.jobs import Jobs
from app.server import make_server, serve_ui
from tests.test_runner import Fakes


@pytest.fixture
def server(cfg):
    jobs = Jobs(cfg, make_steps=Fakes([1, 2]).steps)
    httpd, token = make_server(cfg, port=0, token="tok123", jobs=jobs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, token, cfg
    httpd.shutdown()
    httpd.server_close()


def request(url, data=None, token=None):
    req = urllib.request.Request(url, data=data.encode() if data is not None else None)
    if token:
        req.add_header("X-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.headers, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8")


def test_page_needs_token(server):
    base, token, _ = server
    assert request(f"{base}/")[0] == 403
    assert request(f"{base}/?t=wrong")[0] == 403
    status, headers, body = request(f"{base}/?t={token}")
    assert status == 200 and "<html" in body.lower()
    assert headers["Content-Type"].startswith("text/html")


@pytest.mark.parametrize("path, data", [("/api/cmd", "help"), ("/api/poll?since=0", None), ("/api/export/x.txt", None)])
def test_api_needs_token(server, path, data):
    base, _, _ = server
    assert request(base + path, data)[0] == 403
    assert request(base + path, data, token="wrong")[0] == 403


def test_cmd(server):
    base, token, _ = server
    status, headers, body = request(f"{base}/api/cmd", "help", token)
    assert status == 200 and headers["X-Exit"] == "0" and "run <account>" in body
    status, headers, body = request(f"{base}/api/cmd", "fly", token)
    assert status == 200 and headers["X-Exit"] == "1" and body.startswith("error at line 1")


def test_poll_returns_state_and_new_log(server):
    base, token, _ = server
    request(f"{base}/api/cmd", "run cont\nwait", token)
    status, _, body = request(f"{base}/api/poll?since=0", token=token)
    data = json.loads(body)
    assert status == 200
    assert data["state"]["running"] is False and data["state"]["done"] == 2
    assert data["log"][0] == "> run @cont" and data["next"] == len(data["log"])
    _, _, body = request(f"{base}/api/poll?since={data['next']}", token=token)
    assert json.loads(body)["log"] == []


def test_export_file_route(server):
    base, token, cfg = server
    request(f"{base}/api/cmd", "run cont\nwait\nexport cont", token)
    name = next((cfg.data_dir / "exports").glob("*.txt")).name
    status, headers, body = request(f"{base}/api/export/{name}?t={token}")
    assert status == 200 and body.startswith("TASK:")
    assert headers["Content-Type"].startswith("text/plain")
    (cfg.data_dir / "secret.txt").write_text("secret", encoding="utf-8")
    for bad in ("..%2Fsecret.txt", "..%5Csecret.txt", "nope.txt", "%2E%2E%2Fstate.db"):
        assert request(f"{base}/api/export/{bad}?t={token}")[0] == 404


def test_oversized_script_rejected(server):
    base, token, _ = server
    status, _, body = request(f"{base}/api/cmd", "help\n" * 20000, token)
    assert status == 413 and "too long" in body


def test_bad_since_treated_as_zero(server):
    base, token, _ = server
    assert request(f"{base}/api/poll?since=abc", token=token)[0] == 200


def test_unknown_route_404(server):
    base, token, _ = server
    assert request(f"{base}/api/nothing", token=token)[0] == 404


def test_ctl_file_written_only_with_ctl_and_removed(cfg, monkeypatch):
    ctl_file = cfg.data_dir / "ctl.json"
    seen = {}

    def fake_serve_forever(self, *a, **k):
        seen["exists"] = ctl_file.exists()
        seen["content"] = json.loads(ctl_file.read_text()) if ctl_file.exists() else None

    monkeypatch.setattr("http.server.ThreadingHTTPServer.serve_forever", fake_serve_forever)
    serve_ui(cfg, port=0, open_browser=False, ctl=True)
    assert seen["exists"] and set(seen["content"]) == {"port", "token"}
    assert not ctl_file.exists()

    serve_ui(cfg, port=0, open_browser=False, ctl=False)
    assert seen["exists"] is False
