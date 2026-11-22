"""Sample cropped frames with ffmpeg and skip near-identical ones (step 4)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

from pipeline.config import Config

_DIFF_WIDTH = 160
_CELL = 20  # px, on the downscaled frame


class FfmpegMissing(RuntimeError):
    pass


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FfmpegMissing("ffmpeg not found on PATH. Install it with: winget install Gyan.FFmpeg")


def read_image(path: Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    """cv2.imread that also works with non-ASCII Windows paths."""
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), flags)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")
    return img


def _small_gray(path: Path) -> np.ndarray:
    img = read_image(path, cv2.IMREAD_GRAYSCALE)
    h, w = img.shape
    return cv2.resize(img, (_DIFF_WIDTH, max(1, round(h * _DIFF_WIDTH / w))), interpolation=cv2.INTER_AREA)


def frame_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Largest mean difference (0..1) over a grid of cells.

    A whole-frame mean dilutes a subtitle change on a static background below
    the threshold; the busiest cell keeps it at full strength.
    """
    diff = cv2.absdiff(a, b).astype(np.float32) / 255
    h, w = diff.shape
    rows = max(1, h // _CELL)
    cols = max(1, w // _CELL)
    cells = cv2.resize(diff, (cols, rows), interpolation=cv2.INTER_AREA)
    return float(cells.max())


def drop_near_duplicates(frames: list[Path], threshold: float) -> list[Path]:
    """Keep a frame only if it differs enough from the last kept frame."""
    kept: list[Path] = []
    last = None
    for path in frames:
        cur = _small_gray(path)
        if last is None or cur.shape != last.shape or frame_diff(cur, last) >= threshold:
            kept.append(path)
            last = cur
    return kept


def extract_frames(video: Path, out_dir: Path, cfg: Config) -> list[Path]:
    c = cfg.crop
    vf = (
        f"fps={cfg.fps},"
        f"crop=iw*{c.right - c.left:.4f}:ih*{c.bottom - c.top:.4f}:iw*{c.left:.4f}:ih*{c.top:.4f}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf", vf, str(out_dir / "%05d.png")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-300:]}")
    return drop_near_duplicates(sorted(out_dir.glob("*.png")), cfg.frame_diff_threshold)
