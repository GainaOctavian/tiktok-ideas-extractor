import pytest

from pipeline.config import Crop, load_config


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_gives_defaults(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    assert cfg.fps == 1
    assert cfg.crop == Crop(0.35, 0.85, 0.05, 0.95)
    assert cfg.export_max_chars == 40000
    assert cfg.min_height == 720
    assert cfg.max_attempts == 3


def test_partial_file_overrides_only_given_keys(tmp_path):
    cfg = load_config(write(tmp_path, "fps: 2\n"))
    assert cfg.fps == 2
    assert cfg.min_confidence == 60


def test_unknown_key_rejected(tmp_path):
    with pytest.raises(ValueError, match="fpss"):
        load_config(write(tmp_path, "fpss: 2\n"))


def test_bad_crop_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_config(write(tmp_path, "crop: {top: 0.9, bottom: 0.1, left: 0, right: 1}\n"))


def test_relative_dirs_resolve_next_to_config(tmp_path):
    cfg = load_config(write(tmp_path, "data_dir: d\n"))
    assert cfg.data_dir == tmp_path / "d"
    assert cfg.work_dir == tmp_path / "work"
