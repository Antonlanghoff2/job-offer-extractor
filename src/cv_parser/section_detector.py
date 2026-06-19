# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Section detection helpers for CV documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Literal, Optional, Set


SectionKind = Literal["formations", "competences", "experiences_professionnelles", "excluded", "other"]


@dataclass(frozen=True)
class DetectedSection:
    kind: SectionKind
    raw: str


@dataclass(frozen=True)
class SectionBlock:
    """A detected section block inside a CV."""

    name: str
    heading: str
    lines: List[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


SECTION_ALIASES: Dict[str, Set[str]] = {
    "identity": {"coordonnees", "coordonnées", "profil", "about", "resume", "résumé", "summary"},
    "competences": {"competences", "compétences", "skills", "skill set", "technical skills", "tech stack"},
    "diplomes": {"diplomes", "diplômes", "formation", "education", "etudes", "études", "academique"},
    "experiences": {
        "experiences",
        "expériences",
        "experience professionnelle",
        "professional experience",
        "work experience",
        "parcours professionnel",
    },
    "certifications": {"certifications", "certificats", "licenses", "licences"},
    "projects": {"projets", "projects"},
}


def _normalize_heading(text: str) -> str:
    return re.sub(r"[^a-z]+", " ", text.lower()).strip()


def split_lines(text: str) -> List[str]:
    return [line.strip(" \t-•") for line in text.splitlines() if line.strip()]


def detect_section_name(line: str) -> Optional[str]:
    normalized = _normalize_heading(line)
    for section, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return section
    return None


def detect_section(line: str) -> Optional[DetectedSection]:
    kind = detect_section_name(line)
    if kind is None:
        return None
    return DetectedSection(kind=kind, raw=line.strip())


def detect_sections(text: str) -> Dict[str, List[str]]:
    """Group a CV into sections using simple heading detection."""

    lines = split_lines(text)
    sections: Dict[str, List[str]] = {name: [] for name in SECTION_ALIASES}
    sections["misc"] = []
    current = "misc"

    for line in lines:
        section_name = detect_section_name(line)
        if section_name:
            current = section_name
            continue
        sections.setdefault(current, []).append(line)

    return sections


def iter_section_blocks(text: str) -> List[SectionBlock]:
    sections = detect_sections(text)
    blocks: List[SectionBlock] = []
    for name, lines in sections.items():
        if lines:
            blocks.append(SectionBlock(name=name, heading=name, lines=list(lines)))
    return blocks


def first_lines(text: str, limit: int = 12) -> List[str]:
    return split_lines(text)[: max(limit, 1)]
