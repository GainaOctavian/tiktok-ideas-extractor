import os
import subprocess
import sys
from pathlib import Path

import pytest

import tiktok_ideas
from pipeline.lister import ListingError
from pipeline.state import ClipInfo, State
from tests.test_runner import Fakes

ROOT = Path(tiktok_ideas.__file__).parent


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("data_dir: data\nwork_dir: work\n", encoding="utf-8")
    return path


def seed(tmp_path, done=(), failed=(), pending=(), low=()):
    with State(tmp_path / "data" / "state.db") as s:
        ids = [*done, *(i for i, _ in failed), *pending, *low]
        s.add_listed("cont", [ClipInfo(i, f"u{i}", None, None) for i in ids])
        folder = tmp_path / "data" / "transcripts" / "cont"
        folder.mkdir(parents=True, exist_ok=True)
        for i in done:
            (folder / f"{i}.txt").write_text(f"idea {i} is a long enough idea", encoding="utf-8")
            s.mark_done(i, 30)
        for i in low:
            (folder / f"{i}.txt").write_text("", encoding="utf-8")
            s.mark_done(i, 0)
        for i, error in failed:
            for _ in range(3):
                s.mark_failed(i, error)


def call(capsys, *argv):
    code = tiktok_ideas.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_status_and_reset_output(tmp_path, config, capsys):
    seed(tmp_path, done=["1"], failed=[("2", "DownloadError: HTTP 403")], pending=["3"], low=["4"])
    code, out, _ = call(capsys, "--config", str(config), "status", "@cont")
    assert code == 0
    assert out.splitlines() == [
        "@cont: 4 listed | 2 processed (1 low text) | 2 unexported | 0 exported | 1 failed (1 final) | 1 pending",
        "failed: 2 (3/3) DownloadError: HTTP 403",
        "1 clips failed 3 times and are skipped. Requeue them with: reset cont --failed",
        "low text: 4",
    ]
    code, out, _ = call(capsys, "--config", str(config), "reset", "@cont", "--failed")
    assert (code, out.strip()) == (0, "1 failed clips requeued")
    _, out, _ = call(capsys, "--config", str(config), "status", "@cont")
    assert "| 0 failed (0 final) | 2 pending" in out
    assert "Requeue" not in out


def test_status_counts_exported_as_processed(tmp_path, config, capsys):
    seed(tmp_path, done=["1", "2"])
    call(capsys, "--config", str(config), "export", "cont")
    _, out, _ = call(capsys, "--config", str(config), "status", "cont")
    assert "| 2 processed (0 low text) | 0 unexported | 2 exported |" in out


def test_status_unknown_account(config, capsys):
    code, out, _ = call(capsys, "--config", str(config), "status", "nobody")
    assert code == 0 and "no clips yet" in out


def test_export_command(tmp_path, config, capsys):
    seed(tmp_path, done=["1"])
    code, out, _ = call(capsys, "--config", str(config), "export", "@cont")
    assert code == 0
    path = Path(out.splitlines()[0])
    assert path.parent == tmp_path / "data" / "exports"
    assert "[1]" in path.read_text(encoding="utf-8")
    assert out.splitlines()[-1] == "1 clips exported"
    code, out, _ = call(capsys, "--config", str(config), "export", "@cont")
    assert (code, out.strip()) == (0, "Nothing to export.")


def test_run_command(tmp_path, config, capsys, monkeypatch):
    monkeypatch.setattr(tiktok_ideas, "preflight", lambda cfg: None)
    monkeypatch.setattr(tiktok_ideas, "make_steps", Fakes(["1", "2"]).steps)
    code, out, _ = call(capsys, "--config", str(config), "run", "@cont", "--limit", "1")
    assert code == 0
    assert out.splitlines()[1].startswith("[1/1] 2 done")
    assert (tmp_path / "data" / "transcripts" / "cont" / "2.txt").exists()


def test_ui_command(tmp_path, config, monkeypatch):
    calls = {}
    monkeypatch.setattr(tiktok_ideas, "serve_ui", lambda cfg, port, open_browser, ctl: calls.update(
        data_dir=cfg.data_dir, port=port, open_browser=open_browser, ctl=ctl))
    assert tiktok_ideas.main(["--config", str(config), "ui", "--port", "8765", "--no-browser", "--ctl"]) == 0
    assert calls == {"data_dir": tmp_path / "data", "port": 8765, "open_browser": False, "ctl": True}
    assert tiktok_ideas.main(["--config", str(config), "ui"]) == 0
    assert calls["port"] == 0 and calls["open_browser"] is True and calls["ctl"] is False


def test_listing_error_exit_1(config, capsys, monkeypatch):
    fakes = Fakes([])

    def broken(account, cfg):
        raise ListingError("Could not list @cont: 403. Try: pip install -U yt-dlp, or set cookies_from_browser.")

    fakes.list_clips = broken
    monkeypatch.setattr(tiktok_ideas, "preflight", lambda cfg: None)
    monkeypatch.setattr(tiktok_ideas, "make_steps", fakes.steps)
    code, _, err = call(capsys, "--config", str(config), "run", "cont")
    assert code == 1 and "pip install -U yt-dlp" in err


def test_bad_config_exit_1(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("fpss: 2\n", encoding="utf-8")
    code, _, err = call(capsys, "--config", str(path), "status", "cont")
    assert code == 1 and "fpss" in err


def test_bad_account_exit_2(config, capsys):
    code, _, err = call(capsys, "--config", str(config), "status", "bad name!")
    assert code == 2 and "Not a TikTok account" in err


@pytest.mark.parametrize("command", ["run", "export", "status"])
def test_missing_account_hints_powershell_splatting(config, capsys, command):
    # PowerShell turns an unquoted @name into nothing
    code, _, err = call(capsys, "--config", str(config), command)
    assert code == 2 and "'@name'" in err


def test_account_forms_equivalent(tmp_path, config, capsys):
    seed(tmp_path, done=["1"])
    outs = [call(capsys, "--config", str(config), "status", a)[1] for a in ("@Cont", "cont", "https://www.tiktok.com/@cont")]
    assert outs[0] == outs[1] == outs[2]


def test_non_ascii_output_on_cp1252_console(tmp_path, config):
    seed(tmp_path, failed=[("2", "error “🎮” é")])
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "tiktok_ideas.py"), "--config", str(config), "status", "cont"],
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
