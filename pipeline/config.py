"""Load and validate config.yaml."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Crop:
    top: float
    bottom: float
    left: float
    right: float


@dataclass(frozen=True)
class Config:
    ocr_lang: str = "eng"
    fps: float = 1
    crop: Crop = field(default_factory=lambda: Crop(0.35, 0.85, 0.05, 0.95))
    text_mask: str = "white"
    min_confidence: int = 60
    dedupe_similarity: int = 85
    frame_diff_threshold: float = 0.02
    min_height: int = 720
    cookies_from_browser: str | None = None
    impersonate: str | None = "chrome"
    keep_failed_media: bool = False
    tesseract_cmd: str | None = None
    export_max_chars: int = 40000
    max_attempts: int = 3
    low_text_chars: int = 20
    data_dir: Path = Path("data")
    work_dir: Path = Path("work")


_FIELDS = {f.name for f in dataclasses.fields(Config)}


def load_config(path: Path) -> Config:
    """Read a YAML config; missing file or keys fall back to defaults."""
    path = Path(path)
    raw = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: expected a mapping of settings")

    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        raise ValueError(f"{path}: unknown setting(s): {', '.join(unknown)}")

    values = dict(raw)
    if "crop" in values:
        crop = values["crop"]
        if not isinstance(crop, dict) or set(crop) != {"top", "bottom", "left", "right"}:
            raise ValueError("crop needs exactly top, bottom, left, right")
        values["crop"] = Crop(**{k: float(v) for k, v in crop.items()})

    base = path.parent
    for key in ("data_dir", "work_dir"):
        p = Path(values.get(key, getattr(Config, key)))
        values[key] = p if p.is_absolute() else base / p

    cfg = Config(**values)
    c = cfg.crop
    if not (0 <= c.top < c.bottom <= 1 and 0 <= c.left < c.right <= 1):
        raise ValueError("crop must satisfy 0 <= top < bottom <= 1 and 0 <= left < right <= 1")
    if cfg.text_mask not in ("white", "otsu"):
        raise ValueError("text_mask must be white or otsu")
    if cfg.fps <= 0:
        raise ValueError("fps must be greater than 0")
    return cfg
