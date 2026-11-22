"""List an account's clips with yt-dlp, without downloading (step 1)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

from pipeline.config import Config
from pipeline.state import ClipInfo

_ACCOUNT = re.compile(r"^[a-z0-9._]{2,24}$")
_PROFILE_URL = re.compile(r"^https?://(?:www\.|m\.)?tiktok\.com/@([^/?#]+)", re.IGNORECASE)
HINT = "Try: pip install -U yt-dlp, or set cookies_from_browser in config.yaml."


class ListingError(RuntimeError):
    pass


def normalize_account(raw: str) -> str:
    """'@Name', 'name' or a profile URL -> 'name'."""
    text = raw.strip()
    match = _PROFILE_URL.match(text)
    if match:
        text = match.group(1)
    elif "/" in text:
        raise ValueError(f"Not a TikTok account: {raw!r}")
    name = text.lstrip("@").lower()
    if not _ACCOUNT.match(name):
        raise ValueError(f"Not a TikTok account: {raw!r}")
    return name


class _SilentLogger:
    """yt-dlp prints errors even when quiet; ours are reported once, by the caller."""

    def debug(self, msg: str) -> None:
        pass

    info = warning = error = debug


def base_options(cfg: Config) -> dict:
    opts = {"quiet": True, "no_warnings": True, "logger": _SilentLogger()}
    if cfg.cookies_from_browser:
        opts["cookiesfrombrowser"] = (cfg.cookies_from_browser,)
    if cfg.impersonate:
        # TikTok needs browser impersonation (curl_cffi); yt-dlp's automatic pick breaks profile listing
        opts["impersonate"] = ImpersonateTarget.from_str(cfg.impersonate)
    return opts


def _published(entry: dict) -> str | None:
    if entry.get("timestamp"):
        return datetime.fromtimestamp(entry["timestamp"], tz=timezone.utc).date().isoformat()
    day = entry.get("upload_date")
    if day and len(day) == 8:
        return f"{day[:4]}-{day[4:6]}-{day[6:]}"
    return None


def list_clips(account: str, cfg: Config, ydl_factory=yt_dlp.YoutubeDL) -> list[ClipInfo]:
    opts = {**base_options(cfg), "extract_flat": "in_playlist", "skip_download": True}
    try:
        with ydl_factory(opts) as ydl:
            info = ydl.extract_info(f"https://www.tiktok.com/@{account}", download=False)
    except Exception as e:
        raise ListingError(f"Could not list @{account}: {e}. {HINT}") from e

    entries = [e for e in (info or {}).get("entries") or [] if e and e.get("id")]
    if not entries:
        raise ListingError(f"No clips found for @{account} (private, empty or blocked). {HINT}")

    return [
        ClipInfo(
            id=str(e["id"]),
            url=e.get("url") or f"https://www.tiktok.com/@{account}/video/{e['id']}",
            title=e.get("title"),
            published=_published(e),
        )
        for e in entries
    ]
