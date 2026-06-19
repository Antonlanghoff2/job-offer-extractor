# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Context-aware extraction of professional experience entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .confidence import experience_confidence
from .normalizer import collapse_spaces, normalize_text, parse_date_range
from .skill_extractor import extract_skills_from_text

STRONG_JOB_KEYWORDS = ("développeur", "developpeur", "ingénieur", "ingenieur", "data", "scientist", "analyst", "analyste", "consultant", "chef de projet", "technicien", "régisseur", "regisseur", "administrateur", "architecte", "responsable", "devops", "machine learning")
WEAK_JOB_KEYWORDS = ("son", "video", "vidéo", "lumière", "lumiere", "réseau", "reseau")


@dataclass
class _ExperienceCandidate:
    job_parts: list[str] = field(default_factory=list)
    company_parts: list[str] = field(default_factory=list)
    location_parts: list[str] = field(default_factory=list)
    date_values: list[str] = field(default_factory=list)
    description_parts: list[str] = field(default_factory=list)
    source_lines: list[str] = field(default_factory=list)

    @property
    def warm(self) -> bool:
        return bool(self.company_parts or self.location_parts or self.date_values or self.description_parts)

    def add_job(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.job_parts:
            self.job_parts.append(cleaned)

    def add_company(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.company_parts:
            self.company_parts.append(cleaned)

    def add_location(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.location_parts:
            self.location_parts.append(cleaned)

    def add_date(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.date_values:
            self.date_values.append(cleaned)

    def add_description(self, text: str) -> None:
        cleaned = collapse_spaces(text)
        if cleaned not in self.description_parts:
            self.description_parts.append(cleaned)

    def to_dict(self) -> dict[str, object]:
        job = collapse_spaces(" ".join(self.job_parts))
        company = collapse_spaces(" ".join(self.company_parts)) or None
        location = collapse_spaces(" ".join(self.location_parts)) or None
        start = end = None
        if self.date_values:
            start, end, _ = parse_date_range(" / ".join(self.date_values))
        description = collapse_spaces(" ".join(self.description_parts)) or None
        text_source = "\n".join(self.source_lines).strip()
        skills = extract_skills_from_text(" ".join(filter(None, [job, company, location, description, text_source])), source="experience_professionnelle")
        confidence = experience_confidence(title=bool(job), company=bool(company), date=bool(start or end or self.date_values), description=bool(description), location=bool(location))
        if not job:
            return {}
        return {
            "poste": job,
            "entreprise": company,
            "date_debut": start,
            "date_fin": end,
            "lieu": location,
            "description": description,
            "competences_associees": [skill.nom for skill in skills],
            "texte_source": text_source,
            "confiance": confidence,
        }


def _looks_like_job_title(text: str) -> bool:
    cleaned = collapse_spaces(text)
    lowered = normalize_text(cleaned)
    words = cleaned.split()
    if not lowered or len(words) > 5:
        return False
    if any(separator in cleaned for separator in (",", ";", ":")):
        return False
    if any(keyword in lowered for keyword in STRONG_JOB_KEYWORDS):
        return True
    if any(keyword in lowered for keyword in WEAK_JOB_KEYWORDS):
        role_hints = ("régie", "regie", "ingénieur", "ingenieur", "technicien", "régisseur", "regisseur")
        return any(hint in lowered for hint in role_hints)
    return False


def _looks_like_company(text: str) -> bool:
    cleaned = collapse_spaces(text)
    lowered = normalize_text(cleaned)
    if not lowered:
        return False
    if any(separator in cleaned for separator in (",", ";", ":")):
        return False
    if re.search(r"\b(sas|sarl|sa|groupe|studio|theatre|théâtre|association|mairie|universite|université|ecole|école|institut)\b", lowered):
        return True
    if " / " in cleaned or " — " in cleaned or " - " in cleaned:
        return True
    words = cleaned.split()
    capitalized = sum(1 for word in words if word[:1].isupper())
    return 1 <= len(words) <= 5 and capitalized >= 2


def _looks_like_location(text: str) -> bool:
    lowered = normalize_text(text)
    return bool(re.search(r"\b(paris|lyon|lille|toulouse|nantes|rennes|marseille|nice|bordeaux|grenoble|strasbourg)\b", lowered))


def _split_composite_line(line: str) -> list[str]:
    if re.search(r"\b(?:19|20)\d{2}\b", line):
        return [collapse_spaces(line)]
    parts = [collapse_spaces(part) for part in re.split(r"\s+[—–-]\s+|\s+\|\s+", line) if collapse_spaces(part)]
    if len(parts) > 1:
        return parts
    if line.count(",") == 1 and len(line.split()) <= 6:
        parts = [collapse_spaces(part) for part in line.split(",") if collapse_spaces(part)]
        if len(parts) > 1:
            return parts
    return [collapse_spaces(line)]


def _classify_segment(segment: str, candidate: _ExperienceCandidate | None) -> str:
    if re.search(r"\b(?:19|20)\d{2}\b", segment):
        return "date"
    if _looks_like_job_title(segment):
        return "job"
    if _looks_like_location(segment):
        return "location"
    if candidate is not None and candidate.job_parts and not (candidate.company_parts or candidate.location_parts or candidate.date_values):
        if _looks_like_company(segment):
            return "company"
    if candidate is not None and candidate.job_parts:
        return "description"
    if _looks_like_company(segment):
        return "company"
    if candidate is not None:
        return "description"
    return "other"


def extract_experiences(lines: list[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    candidate: _ExperienceCandidate | None = None
    for line in lines:
        for segment in _split_composite_line(line):
            kind = _classify_segment(segment, candidate)
            if kind == "other":
                continue
            if kind == "job" and candidate is not None and candidate.warm:
                entry = candidate.to_dict()
                if entry:
                    entries.append(entry)
                candidate = _ExperienceCandidate()
            if candidate is None:
                if kind == "job":
                    candidate = _ExperienceCandidate()
                else:
                    continue
            candidate.source_lines.append(segment)
            if kind == "job":
                candidate.add_job(segment)
            elif kind == "company":
                if candidate.job_parts:
                    candidate.add_company(segment)
                else:
                    candidate.add_description(segment)
            elif kind == "location":
                candidate.add_location(segment)
            elif kind == "date":
                candidate.add_date(segment)
            else:
                candidate.add_description(segment)
    if candidate is not None:
        entry = candidate.to_dict()
        if entry:
            entries.append(entry)
    return entries
