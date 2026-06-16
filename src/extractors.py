# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Rule-based extractors to refine raw predictions into structured data."""

from __future__ import annotations

import re
from typing import Dict, List


def extract_title(segments: List[str]) -> str:
    """Return the most likely job title.

    Prefers the segment classified as TITLE; falls back to the first
    segment that starts with a known keyword.

    Parameters
    ----------
    segments : List[str]
        Raw text segments.

    Returns
    -------
    str
        Extracted title (or empty string).
    """
    for seg in segments:
        low = seg.strip().lower()
        if low.startswith(("titre", "poste", "intitulé", "intitule")):
            after = re.split(r":\s*", seg, maxsplit=1)
            if len(after) == 2:
                return after[1].strip()
    return segments[0] if segments else ""


def extract_salary(segments: List[str]) -> str:
    """Extract salary information from candidate segments.

    Looks for known currency patterns.

    Parameters
    ----------
    segments : List[str]
        Segments predicted as SALARY.

    Returns
    -------
    str
        Salary string (or empty).
    """
    if not segments:
        return ""
    best = " ".join(segments)
    best = re.sub(r"\s*:?\s*", " ", best, count=1).strip()
    return best


def extract_location(segments: List[str]) -> str:
    """Extract location (city / region).

    Parameters
    ----------
    segments : List[str]
        Segments predicted as LOCATION.

    Returns
    -------
    str
        Location string.
    """
    return "; ".join(segments) if segments else ""


def extract_skills(segments: List[str]) -> List[str]:
    """Extract individual skills from segments.

    Splits on common separators (comma, bullet, slash, "et", etc.).

    Parameters
    ----------
    segments : List[str]
        Segments predicted as SKILLS.

    Returns
    -------
    List[str]
        Sorted list of cleaned skill tokens.
    """
    skills: List[str] = []
    for seg in segments:
        cleaned = re.sub(r"^[:\s]*compétences?\s*:?\s*", "", seg, flags=re.IGNORECASE)
        parts = re.split(r"[,;/•\-]|\set\s", cleaned)
        for p in parts:
            p = p.strip().strip(".")
            if len(p) > 1:
                skills.append(p)
    return sorted(set(skills))


def extract_contract(segments: List[str]) -> str:
    """Extract contract type.

    Parameters
    ----------
    segments : List[str]
        Segments predicted as CONTRACT.

    Returns
    -------
    str
        Contract description.
    """
    return " ".join(segments) if segments else ""


def extract_experience(segments: List[str]) -> str:
    """Extract experience-level information.

    Parameters
    ----------
    segments : List[str]
        Segments predicted as EXPERIENCE.

    Returns
    -------
    str
        Experience description.
    """
    return " ".join(segments) if segments else ""


def extract_remote(segments: List[str]) -> str:
    """Extract remote-work policy.

    Parameters
    ----------
    segments : List[str]
        Segments predicted as REMOTE.

    Returns
    -------
    str
        Remote policy description.
    """
    return " ".join(segments) if segments else ""


def extract_other(segments: List[str]) -> List[str]:
    """Extract miscellaneous / unclassified information.

    Parameters
    ----------
    segments : List[str]
        Segments predicted as OTHER.

    Returns
    -------
    List[str]
        List of misc items.
    """
    return segments


def extract_all(
    labelled: Dict[str, List[str]],
) -> Dict[str, object]:
    """Run all extractors on a dict of label → segments.

    Parameters
    ----------
    labelled : Dict[str, List[str]]
        Mapping from label to list of raw text segments.

    Returns
    -------
    Dict[str, object]
        Structured extraction result.
    """
    return {
        "title": extract_title(labelled.get("TITLE", [])),
        "salary": extract_salary(labelled.get("SALARY", [])),
        "location": extract_location(labelled.get("LOCATION", [])),
        "skills": extract_skills(labelled.get("SKILLS", [])),
        "contract": extract_contract(labelled.get("CONTRACT", [])),
        "experience": extract_experience(labelled.get("EXPERIENCE", [])),
        "remote": extract_remote(labelled.get("REMOTE", [])),
        "other": extract_other(labelled.get("OTHER", [])),
    }
