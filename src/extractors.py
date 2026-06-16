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
    re.compile(r"lieu\s+du\s+poste\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"lieu\s*:\s*(.+)", re.IGNORECASE),
    re.compile(r"ville\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"r[ée]gion\s*:?\s*(.+)", re.IGNORECASE),
]

_NON_LOCATION_WORDS = frozenset({
    "expérience", "travail", "domicile", "compétence", "anglais",
    "profil", "mission", "présentiel", "télétravail", "remote",
    "distanciel", "poste", "salaire", "rémunération", "avantages",
    "description",
})

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
            if not candidate or re.match(r"\d", candidate):
                continue
            first_word = candidate.split()[0].lower() if candidate.split() else ""
            if first_word in _NON_LOCATION_WORDS:
                continue
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
    result = list(found)
    if "IA" in found and "intelligence artificielle" not in found:
        idx = result.index("IA")
        result.insert(idx + 1, "intelligence artificielle")
    elif "intelligence artificielle" in found and "IA" not in found:
        idx = result.index("intelligence artificielle")
        result.insert(idx + 1, "IA")
    return result


def normalize_remote_label(remote_text: str) -> str | None:
    """Normalize a raw remote string to a canonical label.

    Returns one of ``"télétravail"``, ``"présentiel"``, or ``None``.
    """
    lower = remote_text.lower()
    for key, norm in _REMOTE_NORM.items():
        if key in lower:
            return norm
    return None


# ---------------------------------------------------------------------------
# New public API — called directly by predict.py
# ---------------------------------------------------------------------------

def deduplicate_keep_order(items: list[str]) -> list[str]:
    """Remove duplicates while preserving first-occurrence order."""
    return list(dict.fromkeys(items))


def sort_skills_by_predefined_order(skills: list[str]) -> list[str]:
    """Sort skills by their order in ``KNOWN_SKILLS``.

    Skills not present in the predefined list are kept at the end in
    their original relative order.
    """
    order = {s: i for i, s in enumerate(KNOWN_SKILLS)}
    known = [s for s in KNOWN_SKILLS if s in skills]
    unknown = [s for s in skills if s not in order]
    return known + unknown


_OFFER_NUMBER_PATTERNS = [
    re.compile(r"(?:r[ée]f[ée]rence|ref|num[ée]ro|n[°])\s*(?:offre\s*)?:?\s*([A-Za-z0-9\-_]+)", re.IGNORECASE),
    re.compile(r"(?:job\s*)?id\s*:?\s*([A-Za-z0-9\-_]+)", re.IGNORECASE),
    re.compile(r"in\d{6,}", re.IGNORECASE),
]


def extract_offer_number(text: str) -> str | None:
    """Extract a job-offer reference number.

    Detects patterns like ``Référence : ABC123``, ``Ref : 2024-DEV-45``,
    ``Job ID: 98765``, ``INDEED-abc123``.
    """
    for pat in _OFFER_NUMBER_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip() if m.lastindex else m.group(0).strip()
    return None


def extract_salaries(text: str) -> list[str]:
    """Extract all salary mentions from *text*.

    Returns a deduplicated list of matched strings in order of appearance.
    Overlapping / nested matches are pruned (the longest wins).
    """
    raw_matches: list[tuple[int, int, str]] = []
    for pat in SALARY_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(0).strip()
            if not raw:
                continue
            if re.search(r"(taux\s*journalier|horaire|à\s*l['’]heure)", raw, re.IGNORECASE):
                continue
            raw_matches.append((m.start(), m.end(), raw))

    raw_matches.sort(key=lambda x: x[0])

    non_overlapping: list[str] = []
    last_end = -1
    for start, end, raw in raw_matches:
        if start >= last_end:
            non_overlapping.append(raw)
            last_end = end
        else:
            # Overlapping: keep the longer one
            if non_overlapping and (end - start) > (last_end - (start if non_overlapping else 0)):
                non_overlapping[-1] = raw
                last_end = end

    return deduplicate_keep_order(non_overlapping)


_REMOTE_MODE_PATTERNS = [
    re.compile(r"\b(pr[ée]sentiel)\b", re.IGNORECASE),
    re.compile(r"\bt[ée]l[ée]travail\s+occasionnel\b", re.IGNORECASE),
    re.compile(r"\bt[ée]l[ée]travail\s+partiel\b", re.IGNORECASE),
    re.compile(r"\b100%\s*t[ée]l[ée]travail\b", re.IGNORECASE),
    re.compile(r"\bt[ée]l[ée]travail\b", re.IGNORECASE),
    re.compile(r"\bremote\b", re.IGNORECASE),
    re.compile(r"\bdistanciel\b", re.IGNORECASE),
    re.compile(r"travail\s+(?:a|à)\s+domicile\s+occasionnel", re.IGNORECASE),
]


def extract_remote_mode(text: str) -> str | None:
    """Return a canonical remote label for a single text segment.

    Returns one of ``"présentiel"``, ``"télétravail occasionnel"``,
    ``"télétravail partiel"``, ``"remote"``, or ``None``.
    """
    lower = text.lower()
    if "présentiel" in lower and "télétravail" not in lower and "remote" not in lower and "distanciel" not in lower:
        return "présentiel"
    if re.search(r"\bt[ée]l[ée]travail\s+occasionnel\b", lower) or re.search(r"travail\s+(?:a|à)\s+domicile\s+occasionnel", lower):
        return "télétravail occasionnel"
    if re.search(r"\bt[ée]l[ée]travail\s+partiel\b", lower):
        return "télétravail partiel"
    if re.search(r"\b100%\s*t[ée]l[ée]travail\b", lower) or re.search(r"\bremote\b", lower):
        return "remote"
    if re.search(r"\bt[ée]l[ée]travail\b", lower):
        return "télétravail"
    if re.search(r"\bdistanciel\b", lower):
        return "remote"
    return None


_RESOLVE_REMOTE_COMBINED = {
    "présentiel": "présentiel",
    "télétravail occasionnel": "télétravail occasionnel",
    "télétravail partiel": "télétravail partiel",
    "remote": "remote",
    "télétravail": "remote",
}


def resolve_remote(segment_modes: list[str | None]) -> str | None:
    """Combine remote-mode labels from several segments into one canonical value.

    ``"présentiel"`` + ``"télétravail occasionnel"`` → ``"hybride"``
    Otherwise the most specific non-``None`` label wins.
    """
    present = bool(segment_modes.count("présentiel"))
    has_occasional = any("occasionnel" in (m or "") for m in segment_modes)
    has_remote = any(
        m for m in segment_modes
        if m and m != "présentiel"
    )

    if present and has_occasional:
        return "hybride"
    if present:
        return "présentiel"
    if has_remote:
        for m in segment_modes:
            if m and m != "présentiel":
                return m
    return None


def _is_likely_location(candidate: str) -> bool:
    """Return ``True`` if *candidate* looks like a real location."""
    lower = candidate.lower()
    if any(kw in lower for kw in ("domicile", "pourvoir", "gérer", "présentiel",
                                   "télétravail", "distanciel")):
        return False
    first_word = candidate.split()[0].lower() if candidate.split() else ""
    if first_word in _NON_LOCATION_WORDS:
        return False
    if len(candidate.split()) == 1 and first_word in ("en", "à", "au", "aux", "le", "la", "les", "des"):
        return False
    return True


def extract_hiring_locations(text: str) -> list[str]:
    """Extract all hiring-location mentions from *text*.

    Detects patterns like ``Paris``, ``Saint-Maur-des-Fossés (94)``,
    ``Lieu : Bordeaux``, ``Poste basé à Marseille``.
    """
    results: list[str] = []

    for pat in LOCATION_PREFIX_PATTERNS:
        for m in pat.finditer(text):
            candidate = m.group(1).strip()
            if not candidate or re.match(r"\d", candidate):
                continue
            if _is_likely_location(candidate):
                results.append(candidate)

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if _is_likely_location(line) and _CITY_LIKE.match(line):
            results.append(line)

    return deduplicate_keep_order(results)


_CONTACT_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"0[1-9]\d{8}"),
    re.compile(r"\+33\s*\d\s*\d{2}\s*\d{2}\s*\d{2}\s*\d{2}"),
    re.compile(r"01\s*\d{2}\s*\d{2}\s*\d{2}\s*\d{2}"),
    re.compile(r"https?://[^\s,;)]+"),
    re.compile(r"(?:contact|recruteur|à contacter|interlocuteur)\s*:?\s*(.{3,60}?)(?:\.|,|$)", re.IGNORECASE),
]


def extract_contacts(text: str) -> list[str]:
    """Extract all contact information from *text*.

    Returns emails, French phone numbers, application URLs, and
    recruiter names in order of appearance.
    """
    results: list[str] = []
    for pat in _CONTACT_PATTERNS:
        for m in pat.finditer(text):
            candidate = m.group(1).strip() if m.lastindex else m.group(0).strip()
            if candidate:
                results.append(candidate)
    return deduplicate_keep_order(results)


extract_required_skills = extract_skills
