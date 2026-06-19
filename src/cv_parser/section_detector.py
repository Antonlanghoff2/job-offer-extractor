# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Section detection for French CVs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .normalizer import normalize_section_title

SectionKind = Literal["formations", "competences", "experiences_professionnelles", "excluded", "other"]


@dataclass
class SectionMatch:
    kind: SectionKind
    title: str
    raw: str


ALIASES: dict[SectionKind, set[str]] = {
    "formations": {"formation", "formations", "etudes", "études", "diplomes", "diplômes", "diplomes et formations", "parcours academique", "parcours académique", "parcours scolaire", "certifications"},
    "competences": {"competences", "compétences", "competences techniques", "compétences techniques", "competences professionnelles", "compétences professionnelles", "technologies", "outils", "savoir faire", "savoir-faire", "expertise", "langages", "frameworks"},
    "experiences_professionnelles": {"experience", "experiences", "expérience", "expériences", "experiences professionnelles", "expériences professionnelles", "parcours professionnel", "emplois", "missions", "historique professionnel"},
    "excluded": {"loisirs", "centres interet", "centres d interet", "interets", "intérêts", "references", "références", "contact", "coordonnees", "coordonnées", "langues", "profil", "a propos", "à propos", "presentation", "présentation"},
    "other": set(),
}


def detect_section(line: str) -> SectionMatch | None:
    normalized = normalize_section_title(line)
    if not normalized:
        return None
    for kind in ("formations", "competences", "experiences_professionnelles", "excluded"):
        if normalized in ALIASES[kind]:
            return SectionMatch(kind=kind, title=normalized, raw=line)
    for kind in ("formations", "competences", "experiences_professionnelles", "excluded"):
        aliases = ALIASES[kind]
        if any(normalized.startswith(alias) or alias.startswith(normalized) for alias in aliases if alias):
            if len(normalized.split()) <= 5:
                return SectionMatch(kind=kind, title=normalized, raw=line)
    return None
