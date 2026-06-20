# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Text normalization and date parsing helpers for CV parsing."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import List, Optional, Tuple

_MULTISPACE_RE = re.compile(r"\s+")
_ACCENTS_RE = re.compile(r"[\u0300-\u036f]")


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return _ACCENTS_RE.sub("", normalized)


def normalize_text(text: object) -> str:
    value = "" if text is None else str(text)
    value = strip_accents(value.lower().replace("’", "'"))
    value = re.sub(r"[^a-z0-9+#./\- ]+", " ", value)
    return _MULTISPACE_RE.sub(" ", value).strip()


def collapse_spaces(text: str) -> str:
    return _MULTISPACE_RE.sub(" ", text).strip()


def normalize_section_title(text: object) -> str:
    value = normalize_text(text)
    return re.sub(r"[:：\s]+$", "", value).strip()


def split_clean_lines(text: str) -> List[str]:
    text = text.replace("\r", "\n").replace("\u00a0", " ").replace("\t", " ")
    lines: List[str] = []
    for raw_line in text.split("\n"):
        line = collapse_spaces(raw_line.strip())
        if line:
            lines.append(line)
    return lines


def parse_date_range(text: object) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    value = collapse_spaces("" if text is None else str(text))
    if not value:
        return None, None, None
    normalized = normalize_text(value).replace("aujourdhui", "aujourd'hui")
    year_range = re.search(r"((?:19|20)\d{2})\s*(?:-|–|—|/|à|a)\s*((?:19|20)\d{2}|aujourd'hui|present|présent|maintenant)", normalized)
    if year_range:
        start = year_range.group(1)
        end = year_range.group(2)
        return start, end if re.fullmatch(r"(?:19|20)\d{2}", end) else None, int(start)
    since_match = re.search(r"(?:depuis|since)\s+(.+)$", normalized)
    if since_match:
        start_text = collapse_spaces(since_match.group(1))
        year = re.search(r"(19|20)\d{2}", start_text)
        return start_text, None, int(year.group(0)) if year else None
    month_range = re.search(r"((?:janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre)\s+(?:19|20)\d{2})\s*(?:-|–|—|/|à|a)\s*((?:janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre)\s+(?:19|20)\d{2}|(?:19|20)\d{2}|aujourd'hui|present|présent|maintenant)", normalized)
    if month_range:
        start = collapse_spaces(month_range.group(1))
        end = collapse_spaces(month_range.group(2))
        year = re.search(r"(19|20)\d{2}", start)
        return start, end if re.fullmatch(r"(?:19|20)\d{2}", end) else None, int(year.group(0)) if year else None
    year = re.search(r"(19|20)\d{2}", normalized)
    if year:
        return year.group(0), None, int(year.group(0))
    return value, None, None


def parse_iso_or_year(value: object) -> Optional[str]:
    text = collapse_spaces("" if value is None else str(value))
    if not text:
        return None
    if re.fullmatch(r"(19|20)\d{2}", text):
        return text
    for candidate in (text, text.replace("/", "-"), text.replace("Z", "")):
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text
