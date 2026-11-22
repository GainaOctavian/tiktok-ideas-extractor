import json
import socket
import threading

import pytest

import tiktok_ideas_ctl
from app.jobs import Jobs
from app.server import make_server
from tests.test_runner import Fakes


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("data_dir: data\nwork_dir: work\n", encoding="utf-8")
    return path


@pytest.fixture
def app(tmp_path, config):
    from pipeline.config import load_config

    cfg = load_config(config)
    httpd, token = make_server(cfg, jobs=Jobs(cfg, make_steps=Fakes([1, 2]).steps))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "ctl.json").write_text(json.dumps({"port": httpd.server_address[1], "token": token}))
    yield
    httpd.shutdown()
    httpd.server_close()


def ctl(capsys, *argv):
    code = tiktok_ideas_ctl.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_help(app, config, capsys):
    code, out, _ = ctl(capsys, "--config", str(config), "help")
    assert code == 0 and "run <account> [limit]" in out


def test_several_lines_as_arguments(app, config, capsys):
    code, out, _ = ctl(capsys, "--config", str(config), "run cont 1", "wait", "state")
    assert code == 0
    assert out.splitlines()[0] == "started @cont (limit 1)"
    assert out.splitlines()[2] == "idle"


def test_error_exit_1(app, config, capsys):
    code, out, _ = ctl(capsys, "--config", str(config), "fly")
    assert code == 1 and "error at line 1 (fly)" in out


def test_script_file(app, config, capsys, tmp_path):
    script = tmp_path / "s.txt"
    script.write_text("# check\nstate\nexports\n", encoding="utf-8")
    code, out, _ = ctl(capsys, "--config", str(config), "-f", str(script))
    assert code == 0 and out.splitlines() == ["idle", "no exports"]


def test_no_app_listening(config, capsys):
    code, _, err = ctl(capsys, "--config", str(config), "state")
    assert code == 2 and "python tiktok_ideas.py ui --ctl" in err


def test_stale_ctl_file(tmp_path, config, capsys):
    with socket.socket() as s:  # a port nobody listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "ctl.json").write_text(json.dumps({"port": port, "token": "x"}))
    code, _, err = ctl(capsys, "--config", str(config), "state")
    assert code == 2 and "no app listening" in err


def test_nothing_to_run(config, capsys):
    code, _, err = ctl(capsys, "--config", str(config))
    assert code == 2 and "usage" in err.lower()
