import dataclasses

import cv2
import numpy as np
import pytest
import pytesseract

from pipeline import ocr
from pipeline.ocr import TesseractMissing, configure_tesseract, ocr_frame, preprocess


def text_image(text, fg=255, bg=0, h=120, w=900):
    img = np.full((h, w, 3), bg, dtype=np.uint8)
    cv2.putText(img, text, (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (fg, fg, fg), 3)
    return img


def test_preprocess_doubles_size_and_is_binary():
    img = np.random.default_rng(0).integers(0, 256, (50, 100, 3)).astype(np.uint8)
    out = preprocess(img)
    assert out.shape == (100, 200)
    assert set(np.unique(out)) <= {0, 255}


def test_preprocess_inverts_light_text_on_dark():
    assert preprocess(text_image("ADD A PET")).mean() > 127


def test_preprocess_keeps_dark_text_on_light():
    assert preprocess(text_image("ADD A PET", fg=0, bg=255)).mean() > 127


def fake_data(words, confs, lines=None):
    n = len(words)
    lines = lines or [1] * n
    return {
        "text": words,
        "conf": confs,
        "block_num": [1] * n,
        "par_num": [1] * n,
        "line_num": lines,
    }


def test_low_confidence_words_dropped(tmp_path, cfg, monkeypatch):
    path = tmp_path / "f.png"
    cv2.imwrite(str(path), text_image("x"))
    monkeypatch.setattr(pytesseract, "image_to_data", lambda *a, **k: fake_data(["add", "~~", "pet"], [90, 20, 80]))
    assert ocr_frame(path, cfg) == ["add pet"]


def test_words_grouped_per_line_and_empty_dropped(tmp_path, cfg, monkeypatch):
    path = tmp_path / "f.png"
    cv2.imwrite(str(path), text_image("x"))
    data = fake_data(["add", "", "pet", "trade", "items"], [90, -1, 80, 95, 70], lines=[1, 1, 1, 2, 2])
    monkeypatch.setattr(pytesseract, "image_to_data", lambda *a, **k: data)
    assert ocr_frame(path, cfg) == ["add pet", "trade items"]


def test_missing_tesseract_raises(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(ocr.shutil, "which", lambda _: None)
    monkeypatch.setattr(ocr, "DEFAULT_TESSERACT", tmp_path / "nope.exe")
    with pytest.raises(TesseractMissing, match="winget install UB-Mannheim.TesseractOCR"):
        configure_tesseract(cfg)


@pytest.mark.needs_tesseract
def test_real_ocr_reads_rendered_text(tmp_path, cfg):
    configure_tesseract(cfg)
    path = tmp_path / "f.png"
    cv2.imwrite(str(path), text_image("ADD A DAILY LOGIN STREAK"))
    assert "daily login" in " ".join(ocr_frame(path, cfg)).lower()


@pytest.mark.needs_tesseract
def test_unknown_language_rejected(cfg):
    with pytest.raises(TesseractMissing, match="xyz"):
        configure_tesseract(dataclasses.replace(cfg, ocr_lang="xyz"))
