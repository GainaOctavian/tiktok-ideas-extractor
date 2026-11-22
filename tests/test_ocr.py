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


@pytest.mark.parametrize("mode", ["white", "otsu"])
def test_preprocess_doubles_size_and_is_binary(mode):
    img = np.random.default_rng(0).integers(0, 256, (50, 100, 3)).astype(np.uint8)
    out = preprocess(img, mode)
    assert out.shape == (100, 200)
    assert set(np.unique(out)) <= {0, 255}


@pytest.mark.parametrize("mode", ["white", "otsu"])
def test_preprocess_inverts_light_text_on_dark(mode):
    assert preprocess(text_image("ADD A PET"), mode).mean() > 127


def test_otsu_keeps_dark_text_on_light():
    assert preprocess(text_image("ADD A PET", fg=0, bg=255), "otsu").mean() > 127


def test_white_mask_keeps_white_text_on_red_highlight():
    # karaoke captions: the current word is white on a red box
    img = np.full((120, 900, 3), (200, 180, 160), dtype=np.uint8)  # beige-ish background
    cv2.rectangle(img, (0, 20), (450, 110), (60, 40, 230), -1)  # red box (BGR)
    cv2.putText(img, "ROBLOX", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 3)
    cv2.putText(img, "GAME", (500, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 3)
    out = preprocess(img, "white")
    left, right = out[:, :900], out[:, 1000:]
    # text pixels (dark) exist on both the red box and the background, and nothing else is dark
    assert (left == 0).mean() > 0.02 and (right == 0).mean() > 0.02
    assert (out == 0).mean() < 0.25


def test_white_mask_ignores_saturated_colors():
    img = np.full((60, 100, 3), (60, 40, 230), dtype=np.uint8)  # all red, no text
    assert (preprocess(img, "white") == 0).mean() == 0


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        preprocess(text_image("x"), "magic")


@pytest.mark.needs_tesseract
def test_real_ocr_reads_highlighted_word(tmp_path, cfg):
    configure_tesseract(cfg)
    img = np.full((120, 900, 3), (40, 40, 40), dtype=np.uint8)
    cv2.rectangle(img, (0, 25), (330, 105), (60, 40, 230), -1)
    cv2.putText(img, "ROBLOX GAME TOGETHER", (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 4)
    path = tmp_path / "f.png"
    cv2.imwrite(str(path), img)
    assert "ROBLOX" in " ".join(ocr_frame(path, cfg)).upper()


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
