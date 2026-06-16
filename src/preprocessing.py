# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Text preprocessing utilities for job-offer content."""

from __future__ import annotations

import re
from typing import List, Pattern


FR_SPECIAL_CHARS: Pattern = re.compile(r"[°§«»´`¨^]")
MULTISPACE: Pattern = re.compile(r"[ \t]+")
NON_ALPHA: Pattern = re.compile(r"[^a-zA-Z0-9À-ÖØ-öø-ÿœŒæÆ@\-/._\s]")


def clean_text(raw: str) -> str:
    """Clean a raw text chunk.

    Steps
    -----
    1. Normalise unicode (NFD + remove combining marks).
    2. Remove/swap French special printing characters.
    3. Collapse multiple spaces / tabs.
    4. Strip leading/trailing whitespace.

    Parameters
    ----------
    raw : str
        Input text.

    Returns
    -------
    str
        Cleaned text.
    """
    text = raw.strip()
    text = FR_SPECIAL_CHARS.sub("", text)
    text = MULTISPACE.sub(" ", text)
    return text.strip()


def segment_offer(raw_offer: str) -> List[str]:
    """Split a full job-offer text into line-based segments.

    Each non-empty line is treated as one segment.  This simple strategy
    works well for the structured-but-noisy format of typical French
    job ads (e.g. posted on message boards).

    Parameters
    ----------
    raw_offer : str
        Full job offer text.

    Returns
    -------
    List[str]
        List of cleaned text segments.
    """
    lines = raw_offer.strip().split("\n")
    segments: List[str] = []
    for line in lines:
        line = clean_text(line)
        if line:
            segments.append(line)
    return segments


def label_patterns() -> dict:
    """Return a dict of compiled regex patterns for known field markers.

    These patterns help the rule-based fallback / post-processing step.
    """
    return {
        "title": re.compile(
            r"\b(titre|poste|intitul[ée])\s*:?\s*(.*)", re.IGNORECASE
        ),
        "salary": re.compile(
            r"(salaire|rémunération|fourchette\s*salariale)\s*:?\s*(.*)",
            re.IGNORECASE,
        ),
        "location": re.compile(
            r"(localisation|lieu|adresse|ville|région|département)\s*:?\s*(.*)",
            re.IGNORECASE,
        ),
        "contract": re.compile(
            r"(contrat|type|cdi|cdd|stage|alternance|freelance|mission)\s*:?\s*(.*)",
            re.IGNORECASE,
        ),
        "experience": re.compile(
            r"(expérience|niveau|ancienneté|jeune diplômé|débutant|confirmé|senior)\s*:?\s*(.*)",
            re.IGNORECASE,
        ),
        "skills": re.compile(
            r"(compétences|maîtrise|technologies|langages|outils)\s*:?\s*(.*)",
            re.IGNORECASE,
        ),
        "remote": re.compile(
            r"(télétravail|remote|distanciel)\s*:?\s*(.*)", re.IGNORECASE,
        ),
    }
