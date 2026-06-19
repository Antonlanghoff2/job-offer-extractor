# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Context-aware extraction of French education entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .confidence import education_confidence
from .normalizer import collapse_spaces, normalize_text, parse_date_range

DIPLOMA_KEYWORDS = ("cap", "bep", "bac", "bts", "dut", "but", "licence", "bachelor", "master", "mastère", "mastere", "mba", "doctorat", "diplome", "diplôme", "certificat", "certification", "mooc", "formation", "cursus", "etudes", "études")
INSTITUTION_KEYWORDS = ("université", "universite", "école", "ecole", "lycée", "lycee", "institut", "iut", "télécom", "telecom", "centrale", "openclassrooms", "cnam", "ina", "organisme", "campus")


@dataclass(slots=True)
class _EducationCandidate:
    title_parts: list[str] = field(default_factory=list)
    institution_parts: list[str] = field(default_factory=list)
    description_parts: list[str] = field(default_factory=list)
    date_values: list[str] = field(default_factory=list)
    level: str | None = None
    source_lines: list[str] = field(default_factory=list)

    @property
    def warm(self) -> bool:
        return bool(self.institution_parts or self.description_parts or self.date_values)

    def add_title(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.title_parts:
            self.title_parts.append(cleaned)
        if self.level is None:
            self.level = _extract_level(cleaned)

    def add_institution(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.institution_parts:
            self.institution_parts.append(cleaned)

    def add_description(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.description_parts:
            self.description_parts.append(cleaned)

    def add_date(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.date_values:
            self.date_values.append(cleaned)

    def to_dict(self) -> dict[str, object]:
        title = collapse_spaces(" ".join(self.title_parts))
        institution = collapse_spaces(" ".join(self.institution_parts)) or None
        description = collapse_spaces(" ".join(self.description_parts)) or None
        start = end = None
        year = None
        if self.date_values:
            start, end, year = parse_date_range(" / ".join(self.date_values))
        confidence = education_confidence(title=bool(title), institution=bool(institution), date=bool(start or end or year), description=bool(description))
        if not title:
            title = institution or description or ""
        if not title:
            return {}
        return {
            "intitule": title,
            "etablissement": institution,
            "niveau": self.level,
            "date_debut": start,
            "date_fin": end,
            "annee": year,
            "description": description,
            "texte_source": "\n".join(self.source_lines).strip(),
            "confiance": confidence,
        }


def _has_diploma_keyword(text: str) -> bool:
    lowered = normalize_text(text)
    return any(keyword in lowered for keyword in DIPLOMA_KEYWORDS)


def _has_institution_keyword(text: str) -> bool:
    lowered = normalize_text(text)
    return any(keyword in lowered for keyword in INSTITUTION_KEYWORDS)


def _looks_like_academic_title(text: str) -> bool:
    stripped = collapse_spaces(text)
    if not stripped:
        return False
    lowered = normalize_text(stripped)
    if lowered in {"loisirs", "contact", "profil"}:
        return False
    words = stripped.split()
    if len(words) > 10:
        return False
    if _has_diploma_keyword(stripped):
        return True
    if re.fullmatch(r"[A-Z0-9][A-Z0-9+/-]{1,8}", stripped):
        return True
    capitalized = sum(1 for word in words if word[:1].isupper())
    return capitalized >= max(1, len(words) - 1)


def _looks_like_institution(text: str) -> bool:
    stripped = collapse_spaces(text)
    if not stripped:
        return False
    if _has_institution_keyword(stripped):
        return True
    if "/" in stripped and len(stripped.split()) <= 6:
        return True
    if re.search(r"\b(?:paris|lyon|lille|toulouse|nantes|grenoble|bordeaux|rennes|marseille|nice)\b", normalize_text(stripped)):
        return True
    return any(word.isupper() and len(word) > 1 for word in stripped.split())


def _split_composite_line(line: str) -> list[str]:
    if re.search(r"\b(?:19|20)\d{2}\b", line):
        return [collapse_spaces(line)]
    parts = [collapse_spaces(part) for part in re.split(r"\s+[—–-]\s+", line) if collapse_spaces(part)]
    return parts or [collapse_spaces(line)]


def _extract_level(text: str) -> str | None:
    lowered = normalize_text(text)
    mapping = {
        "mastère spécialisé": "Mastère spécialisé",
        "mastere specialise": "Mastère spécialisé",
        "master": "Master",
        "mba": "MBA",
        "doctorat": "Doctorat",
        "bachelor": "Bachelor",
        "licence": "Licence",
        "bts": "BTS",
        "dut": "DUT",
        "but": "BUT",
        "cap": "CAP",
        "bep": "BEP",
        "bac": "Bac",
        "certification": "Certification",
        "certificat": "Certificat",
        "mooc": "MOOC",
    }
    for keyword, label in mapping.items():
        if keyword in lowered:
            return label
    if "diplome d ingenieur" in lowered or "diplôme d ingénieur" in lowered or "diplôme d'ingénieur" in lowered or "diplome d'ingenieur" in lowered:
        return "Diplôme d’ingénieur"
    return None


def _classify_segment(segment: str, has_candidate: bool) -> str:
    if not segment:
        return "description"
    if re.search(r"\b(?:19|20)\d{2}\b", segment):
        return "date"
    if _has_diploma_keyword(segment):
        return "title"
    if _has_institution_keyword(segment) or _looks_like_institution(segment):
        return "institution"
    if has_candidate and (_looks_like_academic_title(segment) or re.fullmatch(r"[A-Z0-9][A-Z0-9+/-]{1,10}", collapse_spaces(segment))):
        return "title"
    if has_candidate:
        return "description"
    if re.fullmatch(r"[A-Z0-9][A-Z0-9+/-]{1,10}", collapse_spaces(segment)):
        return "title"
    return "other"


def extract_educations(lines: list[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    candidate: _EducationCandidate | None = None
    for line in lines:
        for segment in _split_composite_line(line):
            kind = _classify_segment(segment, candidate is not None)
            if kind == "other":
                continue
            if kind == "title" and candidate is not None and candidate.warm:
                entry = candidate.to_dict()
                if entry:
                    entries.append(entry)
                candidate = _EducationCandidate()
            if candidate is None:
                if kind == "title":
                    candidate = _EducationCandidate()
                else:
                    continue
            candidate.source_lines.append(segment)
            if kind == "title":
                candidate.add_title(segment)
            elif kind == "institution":
                if candidate.title_parts or candidate.warm:
                    candidate.add_institution(segment)
                elif _looks_like_institution(segment):
                    continue
                else:
                    candidate.add_description(segment)
            elif kind == "date":
                candidate.add_date(segment)
            else:
                candidate.add_description(segment)
    if candidate is not None:
        entry = candidate.to_dict()
        if entry:
            entries.append(entry)
    return entries
