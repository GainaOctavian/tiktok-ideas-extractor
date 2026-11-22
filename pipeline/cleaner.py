"""Merge duplicate OCR lines into a per-clip transcript (step 6)."""
from __future__ import annotations

import re
from typing import Iterable

from rapidfuzz import fuzz

MIN_LETTER_RATIO = 0.5  # letters / non-space characters
RECENT_LINES = 8  # kept lines a new line is compared with for build-ups and fragments
_LONE_PIPE = re.compile(r"(?<!\S)\|(?!\S)")
_MONEY = set("$€£%")
_KEEP_SINGLE = {"a", "i"}
_END_PUNCT = ".,!?'\""


def _alnum(token: str) -> int:
    return sum(ch.isalnum() for ch in token)


def _speck(token: str) -> bool:
    """A stray OCR mark: under 2 letters/digits, unless it is an amount like $5 or 5%."""
    if any(ch.isdigit() for ch in token) and _MONEY & set(token):
        return False
    return _alnum(token) < 2


def _zero_as_o(token: str) -> str:
    """Tesseract reads O inside a word as 0 ("T0", "ROBL0X"); leave real numbers ($10k, 2020s) alone."""
    digits = {ch for ch in token if ch.isdigit()}
    if digits == {"0"} and any(ch.isalpha() for ch in token):
        return token.replace("0", "O")
    return token


def _strip_edges(line: str) -> str:
    """Drop OCR specks at the line ends (single symbols, stray letters, glued marks)."""
    tokens = line.split()
    while tokens and _speck(tokens[0]) and tokens[0].lower() not in _KEEP_SINGLE:
        tokens.pop(0)
    while tokens and _speck(tokens[-1]):
        tokens.pop()
    if not tokens:
        return ""
    first = tokens[0]
    while first and not first[0].isalnum():
        first = first[1:]
    tokens[0] = first
    last = tokens[-1]
    while last and not (last[-1].isalnum() or last[-1] in _END_PUNCT or last[-1] in _MONEY):
        last = last[:-1]
    tokens[-1] = last
    return " ".join(t for t in tokens if t)


def _mostly_letters(line: str) -> bool:
    chars = line.replace(" ", "")
    return bool(chars) and sum(ch.isalpha() for ch in chars) / len(chars) >= MIN_LETTER_RATIO


def _normalize(line: str) -> str:
    line = " ".join(line.split())
    if not _mostly_letters(line):
        return ""
    line = _LONE_PIPE.sub("I", line)  # Tesseract reads a standalone capital I as "|"
    line = " ".join(_zero_as_o(t) for t in line.split())
    return _strip_edges(line)


def _words(line: str) -> str:
    """Lowercase words padded with spaces, for whole-word containment checks."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", line.lower())) + " "


def _is_text(line: str) -> bool:
    """Real subtitle text, not an OCR fragment: two words, or one word of 4+ letters, mostly letters."""
    if not _mostly_letters(line):
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
    into their longest version; pieces of a recent line are dropped.
    """
    kept: list[str] = []
    for raw in lines:
        line = _normalize(raw)
        if not _is_text(line):
            continue
        low = line.lower()
        words = _words(line)
        # Recent lines only: other text (UI, a second caption line) can sit between the steps.
        recent = list(range(max(0, len(kept) - RECENT_LINES), len(kept)))

        if any(words in _words(kept[i]) for i in recent):
            continue
        match = next(
            (
                i
                for i in reversed(recent)
                if _words(kept[i]) in words or _extends(kept[i].lower(), low, similarity)
            ),
            None,
        )
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
