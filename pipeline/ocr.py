"""Preprocess frames and OCR them with Tesseract (step 5)."""
from __future__ import annotations

import shutil
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from pipeline.config import Config
from pipeline.frames import read_image

DEFAULT_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


class TesseractMissing(RuntimeError):
    pass


def configure_tesseract(cfg: Config) -> None:
    """Point pytesseract at a working tesseract.exe and check the OCR language."""
    cmd = cfg.tesseract_cmd or shutil.which("tesseract")
    if not cmd and DEFAULT_TESSERACT.exists():
        cmd = str(DEFAULT_TESSERACT)
    if not cmd or (not Path(cmd).exists() and not shutil.which(cmd)):
        raise TesseractMissing(
            "Tesseract not found. Install it with: winget install UB-Mannheim.TesseractOCR, "
            "or set tesseract_cmd in config.yaml."
        )
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        languages = pytesseract.get_languages(config="")
    except Exception as e:
        raise TesseractMissing(f"Tesseract at {cmd} does not run: {e}") from e
    if cfg.ocr_lang not in languages:
        raise TesseractMissing(
            f"Tesseract has no '{cfg.ocr_lang}' language data (has: {', '.join(sorted(languages))})."
        )


TEXT_MASKS = ("white", "otsu")
_WHITE_MAX_SATURATION = 70
_WHITE_MIN_VALUE = 200


def preprocess(img: np.ndarray, mode: str = "white") -> np.ndarray:
    """2x upscale + binarize; returns dark text on a light background.

    white: keep only near-white pixels (TikTok captions are white with a dark outline),
           which also reads words highlighted on a colored box.
    otsu:  grayscale + Otsu threshold, for other caption styles.
    """
    if mode not in TEXT_MASKS:
        raise ValueError(f"text_mask must be one of {', '.join(TEXT_MASKS)}, not {mode!r}")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    if mode == "white":
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = ((hsv[..., 1] < _WHITE_MAX_SATURATION) & (hsv[..., 2] > _WHITE_MIN_VALUE)).astype(np.uint8) * 255
        big = cv2.resize(mask, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, binary = cv2.threshold(big, 127, 255, cv2.THRESH_BINARY)
        return cv2.bitwise_not(binary)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if binary.mean() < 127:
        binary = cv2.bitwise_not(binary)
    return binary


def ocr_frame(path: Path, cfg: Config) -> list[str]:
    data = pytesseract.image_to_data(
        preprocess(read_image(path), cfg.text_mask),
        lang=cfg.ocr_lang,
        config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )
    lines: dict[tuple[int, int, int], list[str]] = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        if not word or float(data["conf"][i]) < cfg.min_confidence:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
    return [" ".join(words) for words in lines.values()]
