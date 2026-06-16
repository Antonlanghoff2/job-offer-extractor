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
    "IA", "intelligence artificielle", "machine learning", "deep learning",
    "imagerie", "optique", "instrumentation", "vision",
    "traitement d'images", "acquisition", "diagnostic optique",
    "gestion de projet", "pilotage projet",
    "qualité", "coûts", "délais", "relation client",
    "anglais professionnel",
    "ferroviaire", "aéronautique", "recherche scientifique",
]

_SKILL_PATTERNS = [
    (re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE), s)
    for s in KNOWN_SKILLS
]

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
    re.compile(r"lieu\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"ville\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"r[ée]gion\s*:?\s*(.+)", re.IGNORECASE),
]

_NOISE_SECTION_HEADERS = frozenset({
    "Salaire", "Type de poste", "Lieu",
    "Avantages", "Description du poste",
    "Profil recherché", "Vos missions",
    "Pourquoi rejoindre", "Détails de l'emploi",
    "Correspondance entre ce poste et votre profil",
})

_COMPANY_LEGAL_FORMS = re.compile(
    r"\b(SAS|SARL|EURL|SA|SCOP|EI|EIRL|SELARL|SASU|SNC|SCP)\b", re.IGNORECASE
)

_TITLE_SUFFIX = re.compile(r"\s*-\s*job\s*post\s*$", re.IGNORECASE)

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
    re.compile(r"(exp[ée]rience\s+significative\s+[^,.\n]+)", re.IGNORECASE),
]

_REMOTE_PATTERNS = [
    re.compile(r"\b(t[ée]l[ée]travail\s*[^,.\n]*)", re.IGNORECASE),
    re.compile(r"(\d+%\s*(?:remote|t[ée]l[ée]travail|distanciel))", re.IGNORECASE),
    re.compile(r"\b((?:\d+\s+)?remote[^,.\n]*)", re.IGNORECASE),
    re.compile(r"\b(distanciel\s*[^,.\n]*)", re.IGNORECASE),
    re.compile(r"\b(pr[ée]sentiel\s*[^,.\n]*)", re.IGNORECASE),
    re.compile(r"(travail\s+(?:a|à)\s+domicile\s*[^,.\n]*)", re.IGNORECASE),
]

_REMOTE_NORM = {
    "télétravail": "télétravail",
    "remote": "télétravail",
    "distanciel": "télétravail",
    "présentiel": "présentiel",
    "travail à domicile": "télétravail",
}

_COMPANY_PREFIX = re.compile(
    r"(?:entreprise|société|societe|employeur)\s*:?\s*(.+)", re.IGNORECASE
)

# Regex for city-like patterns: "Paris", "Lyon (69)", "Saint-Maur-des-Fossés (94)"
_CITY_LIKE = re.compile(
    r"^[A-ZÀ-Œ][A-Za-zÀ-ÿ\-]+(?:\s+[A-Za-zÀ-ÿ\-]+)*\s*(?:\(\d{2,3}\))?$"
)

# Words that when alone or with just one companion word are NOT a title
_SHORT_TITLE_BLACKLIST = frozenset({
    "cdi", "cdd", "stage", "freelance", "alternance", "intérim", "à pourvoir",
    "urgent", "h/f", "temps plein", "temps partiel",
})


def clean_text(text: str) -> str:
    """Normalize and clean a text segment.

    Strips HTML artifacts (``&nbsp;``), non-breaking spaces (\\xa0),
    useless bullets (•, -, * at line start), and collapses whitespace.
    """
    t = text.replace("\xa0", " ").replace("&nbsp;", " ")
    t = re.sub(r"^[\s•\-*]+\s*", "", t)
    t = re.sub(r"\s+", " ", t.strip())
    return t


def split_offer_into_segments(text: str) -> list[str]:
    """Split a raw job offer into non-empty cleaned text segments."""
    return [clean_text(line) for line in text.strip().split("\n") if clean_text(line)]


def is_noise_segment(segment: str) -> bool:
    """Return True when *segment* is a section header or generic noise.

    These are headings that appear in structured job offers but carry
    no extractable value on their own.
    """
    s = segment.strip().rstrip(":").strip()
    if s in _NOISE_SECTION_HEADERS:
        return True
    if s.upper() == s and len(s.split()) <= 4 and len(s) > 2:
        if any(kw in s.lower() for kw in ("mission", "profil", "description", "poste")):
            return True
    return False


def is_probable_company_name(segment: str) -> bool:
    """Return True when *segment* is likely a company name rather than a title.

    Heuristics
    ----------
    * Contains a legal form abbreviation (``SAS``, ``SARL``, …).
    * Is short (≤3 words) with an ampersand (``&``) and no comma.
    * Is short, starts with uppercase, and doesn't look like a title.
    """
    s = segment.strip()
    if not s:
        return False
    if _COMPANY_LEGAL_FORMS.search(s):
        return True
    words = s.split()
    if len(words) > 4:
        return False
    if "&" in s and "," not in s and 1 <= len(words) <= 4:
        return True
    if 1 <= len(words) <= 3 and s[0].isupper():
        lower = s.lower()
        title_kw = (
            "développeur", "ingénieur", "chef", "responsable", "directeur",
            "chargé", "consultant", "manager", "architecte", "technicien",
            "data", "devops", "lead", "product", "full stack",
        )
        if not any(lower.startswith(kw) for kw in title_kw):
            return True
    return False


def extract_company(text: str) -> str | None:
    """Extract a company name from a segment via explicit prefixes."""
    m = _COMPANY_PREFIX.search(text)
    return m.group(1).strip() if m else None


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
    exclusion = re.search(
        r"(répondu\s+à|candidatures?\s*[aà]|jours?\s*(?:de|par))", text, re.IGNORECASE
    )
    if exclusion:
        return None

    for pattern in LOCATION_PREFIX_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            if candidate and not re.match(r"\d", candidate):
                return candidate

    if _CITY_LIKE.match(text.strip()):
        return text.strip()

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
    """Extract known domain skills from text. Returns list (possibly empty)."""
    found: list[str] = []
    for pat, name in _SKILL_PATTERNS:
        if pat.search(text):
            found.append(name)
    return found


def normalize_remote_label(remote_text: str) -> str | None:
    """Normalize a raw remote string to a canonical label.

    Returns one of ``"télétravail"``, ``"présentiel"``, or ``None``.
    """
    lower = remote_text.lower()
    for key, norm in _REMOTE_NORM.items():
        if key in lower:
            return norm
    return None
