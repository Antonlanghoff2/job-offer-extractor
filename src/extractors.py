# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Rule-based extractors for raw job-offer text."""

from __future__ import annotations

import re
from typing import List


KNOWN_SKILLS = [
    "Python", "Django", "Flask", "FastAPI",
    "PHP", "Symfony",
    "JavaScript", "TypeScript", "React", "Vue",
    "SQL", "PostgreSQL", "MySQL",
    "Docker", "Git", "Linux",
    "AWS", "Azure",
    "Machine Learning", "scikit-learn", "PyTorch", "TensorFlow",
    "Pandas", "NumPy",
]

_SKILL_PATTERNS = [(re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE), s) for s in KNOWN_SKILLS]

CONTRACT_KEYWORDS = ["CDI", "CDD", "freelance", "alternance", "stage", "intérim"]

SALARY_PATTERNS = [
    re.compile(
        r"(?:entre|de)?\s*(\d{2,3})\s*[kK]\s*€?\s*(?:et|à|-|au)\s*(\d{2,3})\s*[kK]\s*€?"
    ),
    re.compile(r"(\d{2,3})\s*[-–]\s*(\d{2,3})\s*[kK]\s*€?"),
    re.compile(
        r"(?:entre|de)?\s*(\d[\d\s]{3,})\s*(?:€\s*)?(?:et|à)\s*(\d[\d\s]{3,})\s*€"
    ),
    re.compile(r"(\d[\d\s]{3,})\s*[-–]\s*(\d[\d\s]{3,})\s*€"),
    re.compile(r"(\d{2,3})\s*[kK]\s*€?"),
    re.compile(r"(\d[\d\s]{3,})\s*€(?:\s*brut)?"),
]

LOCATION_PREFIX_PATTERNS = [
    re.compile(r"(?:poste\s+)?bas[ée]\s+(?:a|à|sur)\s+(.+)", re.IGNORECASE),
    re.compile(r"localisation\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"(?:a|à)\s+([A-ZÀ-Œ][a-zà-ÿ]+(?:[\s-][A-Za-zà-ÿ0-9]+)*)", re.IGNORECASE),
    re.compile(r"lieu\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"ville\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"r[ée]gion\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"d[ée]partement\s*:?\s*(.+)", re.IGNORECASE),
]

_EXPERIENCE_PATTERNS = [
    re.compile(r"(\d+\s*(?:a|à)\s*\d+\s*ans?\s*d'exp[ée]rience)", re.IGNORECASE),
    re.compile(r"(\d+\s*ans?\s*(?:minimum|d'exp[ée]rience|requis|souhait[ée]))", re.IGNORECASE),
    re.compile(r"(jeune\s*dipl[ôo]m[ée])", re.IGNORECASE),
    re.compile(r"\b(d[ée]butant)\b", re.IGNORECASE),
    re.compile(r"\b(confirm[ée])\b", re.IGNORECASE),
    re.compile(r"\b(senior)\b", re.IGNORECASE),
    re.compile(r"\b(junior)\b", re.IGNORECASE),
    re.compile(r"\b(exp[ée]rience\s+(?:en|de|dans|pro|significative|souhait[ée]|exig[ée]|minimum|requise|professionnelle|acquise|similaire)\s*\S[^,.\n]*)", re.IGNORECASE),
    re.compile(r"(profil\s+(?:junior|senior|confirm[ée]))", re.IGNORECASE),
    re.compile(r"(plus\s+de\s+\d+\s*ans)", re.IGNORECASE),
]

_REMOTE_PATTERNS = [
    re.compile(r"\b(t[ée]l[ée]travail\s*[^,.\n]*)", re.IGNORECASE),
    re.compile(r"(\d+%\s*(?:remote|t[ée]l[ée]travail|distanciel))", re.IGNORECASE),
    re.compile(r"\b((?:\d+\s+)?remote[^,.\n]*)", re.IGNORECASE),
    re.compile(r"\b(distanciel\s*[^,.\n]*)", re.IGNORECASE),
    re.compile(r"\b(pr[ée]sentiel\s*[^,.\n]*)", re.IGNORECASE),
]


def clean_text(text: str) -> str:
    """Normalize whitespace and strip a text segment."""
    return re.sub(r"\s+", " ", text.strip())


def split_offer_into_segments(text: str) -> list[str]:
    """Split a raw job offer into non-empty cleaned text segments."""
    return [clean_text(line) for line in text.strip().split("\n") if line.strip()]


def extract_salary(text: str) -> str | None:
    """Extract salary information from text. Returns None if not found."""
    if re.search(r"(taux\s*journalier|horaire|à\s*l['’]heure)", text, re.IGNORECASE):
        return None
    for pattern in SALARY_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def extract_contract(text: str) -> str | None:
    """Extract contract type. Returns None if not found."""
    for kw in CONTRACT_KEYWORDS:
        match = re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def extract_location(text: str) -> str | None:
    """Extract location. Returns None if not found."""
    for pattern in LOCATION_PREFIX_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def extract_experience(text: str) -> str | None:
    """Extract experience level. Returns None if not found."""
    for pattern in _EXPERIENCE_PATTERNS:
        match = pattern.search(text)
        if match:
            start = match.start()
            prefix = text[max(0, start - 8):start].strip().lower()
            if prefix in ("no", "pas", "sans", "non") or any(
                prefix.endswith(w) for w in (" no", " pas", " sans", " non")
            ):
                continue
            return match.group(1).strip() if match.lastindex else match.group(0).strip()
    return None


def extract_remote(text: str) -> str | None:
    """Extract remote-work information. Returns None if not found."""
    for pattern in _REMOTE_PATTERNS:
        match = pattern.search(text)
        if match:
            start = match.start()
            prefix = text[max(0, start - 8):start].strip().lower()
            if prefix in ("no", "pas", "sans", "non") or any(
                prefix.endswith(w) for w in (" no", " pas", " sans", " non")
            ):
                continue
            return match.group(1).strip() if match.lastindex else match.group(0).strip()
    return None


def extract_skills(text: str) -> list[str]:
    """Extract known skills from text. Returns list (possibly empty)."""
    found: list[str] = []
    for pat, name in _SKILL_PATTERNS:
        if pat.search(text):
            found.append(name)
    return found


if __name__ == "__main__":
    print("=== extract_salary ===")
    for s in [
        "Salaire entre 38k€ et 45k€ selon profil",
        "Rémunération : de 50 000 à 65 000 € brut annuel",
        "Fourchette salariale 40-55 K€",
        "35 000 € par an brut",
        "Package annuel : 70k€ fixe + bonus",
        "Taux journalier entre 400 et 550 €",
        "no salary here",
    ]:
        print(f"  {s!r} -> {extract_salary(s)!r}")

    print("\n=== extract_contract ===")
    for s in [
        "Contrat CDI temps plein",
        "CDD de 12 mois renouvelable",
        "Stage conventionné de 6 mois",
        "Mission freelance longue durée",
        "Intérim 6 mois",
        "no contract here",
    ]:
        print(f"  {s!r} -> {extract_contract(s)!r}")

    print("\n=== extract_location ===")
    for s in [
        "Poste basé à Paris 11e",
        "localisation : Lyon",
        "à Marseille centre-ville",
        "Région parisienne",
        "no location here",
    ]:
        print(f"  {s!r} -> {extract_location(s)!r}")

    print("\n=== extract_experience ===")
    for s in [
        "3 ans d'expérience minimum",
        "Jeune diplômé accepté",
        "De 5 à 8 ans d'expérience souhaitée",
        "Débutant accepté, formation interne",
        "Senior avec 10 ans d'expérience",
        "Profil junior à confirmé",
        "no experience here",
    ]:
        print(f"  {s!r} -> {extract_experience(s)!r}")

    print("\n=== extract_remote ===")
    for s in [
        "Télétravail possible deux jours par semaine",
        "100% remote autorisé",
        "Présentiel uniquement",
        "Télétravail partiel en hybride",
        "En full remote depuis n'importe où en France",
        "no remote here",
    ]:
        print(f"  {s!r} -> {extract_remote(s)!r}")

    print("\n=== extract_skills ===")
    for s in [
        "Compétences requises : Python, SQL, Docker, Git",
        "Python scikit-learn pandas tensorflow",
        "React, TypeScript, Redux",
        "AWS Azure Machine Learning",
        "no skills here",
    ]:
        print(f"  {s!r} -> {extract_skills(s)!r}")

    print("\n=== split_offer_into_segments ===")
    offer = "Développeur Python\nTélétravail partiel\nSalaire 45k€\n"
    print(f"  {offer!r} -> {split_offer_into_segments(offer)!r}")

    print("\n=== clean_text ===")
    print(f"  {'  hello   world  '!r} -> {clean_text('  hello   world  ')!r}")
