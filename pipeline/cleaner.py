"""Merge duplicate OCR lines into a per-clip transcript (step 6)."""
from __future__ import annotations

import re
from typing import Iterable

from rapidfuzz import fuzz

MIN_LETTER_RATIO = 0.5  # letters / non-space characters
RECENT_LINES = 5  # kept lines a build-up subtitle may extend
_LONE_PIPE = re.compile(r"(?<!\S)\|(?!\S)")


def _normalize(line: str) -> str:
    # Tesseract reads a standalone capital I as "|"
    return _LONE_PIPE.sub("I", " ".join(line.split()))


def _is_text(line: str) -> bool:
    """Real subtitle text, not an OCR fragment: two words, or one word of 4+ letters, mostly letters."""
    chars = line.replace(" ", "")
    letters = sum(ch.isalpha() for ch in chars)
    if not chars or letters / len(chars) < MIN_LETTER_RATIO:
        return False
    words = [sum(ch.isalpha() for ch in token) for token in line.split()]
    return sum(n >= 2 for n in words) >= 2 or any(n >= 4 for n in words)


def _extends(a: str, b: str, similarity: int) -> bool:
    """True if the shorter line is (fuzzily) the start of the longer one."""
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return fuzz.ratio(short, long[: len(short)]) >= similarity


def clean_lines(lines: Iterable[str], similarity: int) -> list[str]:
    """Drop fragments and merge near-duplicates, keeping order of first appearance.

    Subtitles that build up word by word ("add a", "add a daily", ...) collapse
    into their longest version.
    """
    kept: list[str] = []
    for raw in lines:
        line = _normalize(raw)
        if not _is_text(line):
            continue
        low = line.lower()

        # Recent lines only: other text (UI, a second caption line) can sit between the steps.
        recent = range(max(0, len(kept) - RECENT_LINES), len(kept))
        match = next((i for i in reversed(recent) if _extends(kept[i].lower(), low, similarity)), None)
        if match is not None:
            if len(line) > len(kept[match]):
                kept[match] = line
            continue

        for i, k in enumerate(kept):
            if fuzz.ratio(low, k.lower()) >= similarity:
                if len(line) > len(k):
                    kept[i] = line
                break
        else:
            kept.append(line)
    return kept
