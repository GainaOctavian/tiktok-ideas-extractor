"""Download one clip at the smallest resolution that is still >= min_height (step 3)."""
from __future__ import annotations

from pathlib import Path

import yt_dlp

from pipeline.config import Config
from pipeline.lister import base_options

_PARTIAL = {".part", ".ytdl", ".temp"}


class DownloadError(RuntimeError):
    pass


def download(url: str, dest_dir: Path, cfg: Config, ydl_factory=yt_dlp.YoutubeDL) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        **base_options(cfg),
        "format": "b/bv*+ba",
        # '+res:N' = prefer the smallest resolution >= N (res is the short side, so 720x1280 is 720p)
        "format_sort": [f"+res:{cfg.min_height}"],
        "outtmpl": str(dest_dir / "video.%(ext)s"),
        "noprogress": True,
    }
    try:
        with ydl_factory(opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise DownloadError(str(e)) from e

    files = [p for p in dest_dir.glob("video.*") if p.suffix not in _PARTIAL and p.is_file()]
    if len(files) != 1:
        raise DownloadError(f"Expected one downloaded video in {dest_dir}, found {len(files)}")
    return files[0]
