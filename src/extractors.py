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
    "diplôme de chirurgien-dentiste",
    "omnipraticien",
    "plateau technique",
    "assistante dentaire",
    "réglementation médicale",
    "langue française",
    "démarches administratives",
    "développement", "data", "sécurité informatique",
    "protection des données", "analyse", "informatique",
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
    re.compile(r"(?:\d+%?\s*et\s+)*\d+%\s*bruts?/mois"),
    re.compile(r"(?:\b(?:minimum\s+(?:garanti\s+)?)?\d[\d\s]{3,}\s*€/mois)"),
    re.compile(
        r"\d[\d\s]{3,},?\d*\s*€\s*par\s+mois",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:a|à)\s+partir\s+de\s+\d[\d\s]{3,},?\d*\s*€\s*par\s+mois",
        re.IGNORECASE,
    ),
]

LOCATION_PREFIX_PATTERNS = [
    re.compile(r"(?:poste\s+)?bas[ée]\s+(?:a|à|sur)\s+(.+)", re.IGNORECASE),
    re.compile(r"localisation\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"lieu\s+du\s+poste\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"lieu\s*:\s*(.+)", re.IGNORECASE),
    re.compile(r"ville\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"r[ée]gion\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"situ[ée]\s+(?:a|à)\s+([A-Za-zÀ-ÿ\-]+)", re.IGNORECASE),
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
    "Les missions du poste", "Présentation du poste",
    "Rémunération", "Description de la structure",
    "Avantages du poste", "Le profil recherché",
    "L'entreprise",
})

_FORBIDDEN_SECTIONS = frozenset({
    "les missions du poste", "présentation du poste",
    "rémunération", "description de la structure",
    "avantages du poste", "le profil recherché",
    "l'entreprise", "salaire", "type de poste",
    "lieu", "avantages",
})

_FORBIDDEN_TITLES: frozenset = frozenset({
    "Détails de l'emploi",
    "Correspondance entre ce poste et votre profil.",
    "Salaire",
    "Type de poste",
    "Lieu",
    "Avantages",
    "Extraits de la description complète du poste",
    "Description du poste",
    "À propos du poste",
    "Responsabilités",
    "Profil recherché",
    "Type d'emploi",
    "Rémunération",
    "Capacité à faire le trajet ou à déménager",
    "Question(s) de présélection",
    "Formation",
    "Langue",
})

_NON_TITLE_STARTS: frozenset = frozenset({
    "sécurité", "développement", "protection", "correspondance",
    "extraits", "description", "à propos", "responsabilités",
    "profil", "type", "rémunération", "capacité", "question",
    "formation", "langue", "détails", "salaire", "lieu", "avantages",
    "poste", "mission", "compétence", "pourquoi",
    "vous", "enfin", "ce", "cette", "dans", "avec", "pour",
    "afin", "notre", "leur", "nous", "il", "elle", "qui",
})

_NON_CITY_WORDS = frozenset({
    "patients", "soins", "chirurgie", "gestion", "charge", "dossier",
    "mission", "profil", "poste", "salaire", "rémunération",
    "diplôme", "formation", "expérience", "compétence",
    "assistante", "personnel", "administratif", "flux",
    "prise", "courants", "omni", "praticien", "plateau",
    "technique", "moderne", "recrute", "cabinet",
    "langue", "française", "démarches",
    "développement", "analyse", "solutions", "data",
    "sécurité", "informatique", "protection", "enjeux",
    "relationnel", "transversal",
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

_CITY_LIKE = re.compile(
    r"^[A-ZÀ-Œ][A-Za-zÀ-ÿ\-]+(?:\s+[A-Za-zÀ-ÿ\-]+)*\s*(?:\(\d{2,3}\))?$"
)

_DEPARTMENT_LINE = re.compile(
    r"^[A-Za-zÀ-ÿ\-]+(?:\s*-\s*\d{2,3})$"
)

_POSTAL_CODE_LINE = re.compile(
    r"^[A-Za-zÀ-ÿ\- ]+,\s*\d{5}$"
)

_POSTAL_CODE_FIRST = re.compile(
    r"^\d{5}\s+[A-Za-zÀ-ÿ\- ]+$"
)

_FRENCH_POSTAL_CODE = re.compile(r"\b\d{5}\b")

_SHORT_TITLE_BLACKLIST = frozenset({
    "cdi", "cdd", "stage", "freelance", "alternance", "intérim", "à pourvoir",
    "urgent", "h/f", "temps plein", "temps partiel",
})

_SECTOR_BULLET = re.compile(r"•|●|▸|›|♦")


def clean_text(text: str) -> str:
    t = text.replace("\xa0", " ").replace("&nbsp;", " ")
    t = re.sub(r"^[\s•\-*]+\s*", "", t)
    t = re.sub(r"\s+", " ", t.strip())
    return t


def split_offer_into_segments(text: str) -> list[str]:
    return [clean_text(line) for line in text.strip().split("\n") if clean_text(line)]


def is_section_header(segment: str) -> bool:
    s = segment.strip().rstrip(":").strip()
    if s in _NOISE_SECTION_HEADERS:
        return True
    lower = s.lower()
    if lower in _FORBIDDEN_SECTIONS:
        return True
    if s.upper() == s and len(s.split()) <= 4 and len(s) > 2:
        if any(kw in lower for kw in ("mission", "profil", "description", "poste", "rémun", "salaire")):
            return True
    return False


def is_contract_line(segment: str) -> bool:
    s = segment.strip().lower()
    if s in ("cdi", "cdd", "stage", "freelance", "alternance", "intérim", "vié", "vacation"):
        return True
    for kw in CONTRACT_KEYWORDS:
        if s == kw.lower():
            return True
    return False


def is_degree_line(segment: str) -> bool:
    s = segment.strip().lower()
    if re.match(r"^(bac\s*)\+?\d+", s):
        return True
    if re.match(r"^(master|doctorat|licence|bts|dut|ingénieur|cap|baccalauréat)", s):
        return True
    if re.match(r"^niveau\s+(bac\s*\+?\d+|master|doctorat)", s):
        return True
    return False


def is_experience_line(segment: str) -> bool:
    s = segment.strip().lower()
    if re.match(r"^exp[ée]rience", s):
        return True
    if re.match(r"^(exp\.|expérience)\s+\d+", s):
        return True
    if re.match(r"^\d+\s*(a|à)\s*\d+\s*ans", s):
        return True
    if re.match(r"^(débutant|junior|confirmé|senior)\s*$", s):
        return True
    return False


def is_sector_line(segment: str) -> bool:
    s = segment.strip()
    if _SECTOR_BULLET.search(s):
        return True
    lower = s.lower()
    sector_kw = [
        "santé", "social", "association", "service", "industrie",
        "commerce", "informatique", "banque", "assurance", "bâtiment",
        "transport", "logistique", "agriculture", "énergie",
        "services aux entreprises",
    ]
    for kw in sector_kw:
        if lower.startswith(kw) or lower == kw:
            return True
    return False


def is_probable_location(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if re.match(r"^\d{5}\s", s):
        return True
    if _DEPARTMENT_LINE.match(s):
        return True
    if _CITY_LIKE.match(s):
        return True
    lower = s.lower()
    if any(lower.startswith(p) for p in ("situé", "localisation", "lieu", "poste basé", "ville")):
        return True
    return False


def is_noise_segment(segment: str) -> bool:
    s = segment.strip().rstrip(":").strip()
    if s in _NOISE_SECTION_HEADERS:
        return True
    lower = s.lower()
    if lower in _FORBIDDEN_SECTIONS:
        return True
    if s.upper() == s and len(s.split()) <= 4 and len(s) > 2:
        if any(kw in lower for kw in ("mission", "profil", "description", "poste")):
            return True
    return False


def is_probable_company_name(segment: str) -> bool:
    s = segment.strip()
    if not s:
        return False
    if _DEPARTMENT_PATTERN.match(s):
        return False
    if re.search(r"\(\d{2,3}\)", s):
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
            "chirurgien", "dentiste", "médecin", "infirmier", "pharmacien",
        )
        if not any(lower.startswith(kw) for kw in title_kw):
            return True
    return False


def extract_company(text: str) -> str | None:
    m = _COMPANY_PREFIX.search(text)
    return m.group(1).strip() if m else None


def extract_salary(text: str) -> str | None:
    if re.search(r"(taux\s*journalier|horaire|à\s*l['’]heure)", text, re.IGNORECASE):
        return None
    for pattern in SALARY_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def extract_contract(text: str) -> str | None:
    for kw in CONTRACT_KEYWORDS:
        match = re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def extract_location(text: str) -> str | None:
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
    lower = remote_text.lower()
    for key, norm in _REMOTE_NORM.items():
        if key in lower:
            return norm
    return None


def deduplicate_keep_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def sort_skills_by_predefined_order(skills: list[str]) -> list[str]:
    order = {s: i for i, s in enumerate(KNOWN_SKILLS)}
    known = [s for s in KNOWN_SKILLS if s in skills]
    unknown = [s for s in skills if s not in order]
    return known + unknown


_OFFER_NUMBER_PATTERNS = [
    re.compile(
        r"\b(r[ée]f[ée]rence|ref)\s*(?:offre\s*)?:?\s*([A-Za-z0-9\-_]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(num[ée]ro|n°)\s*(?:offre\s*)?:?\s*([A-Za-z0-9\-_]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(offre\s*n°)\s*:?\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(job\s*id|id\s*offre)\s*:?\s*([A-Za-z0-9\-_]+)",
        re.IGNORECASE,
    ),
]


def extract_offer_number(text: str) -> str | None:
    for pat in _OFFER_NUMBER_PATTERNS:
        m = pat.search(text)
        if m:
            groups = m.groups()
            return groups[-1].strip()
    return None


def extract_salaries(text: str) -> list[str]:
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
            if non_overlapping and (end - start) > (last_end - (start if non_overlapping else 0)):
                non_overlapping[-1] = raw
                last_end = end

    return deduplicate_keep_order([normalize_salary(s) for s in non_overlapping])


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


_TITLE_LIKE_STARTS = (
    "développeur", "ingénieur", "chef", "responsable", "directeur",
    "chargé", "consultant", "manager", "architecte", "technicien",
    "data", "devops", "lead", "product", "full stack",
    "chirurgien", "dentiste", "médecin",
)

_NON_GEO_CONTENT = (
    "contactez", "nous au", "téléphone", "email", "recrute",
    "cabinet", "patients", "soins", "chirurgie", "gestion", "dossier",
    "mission", "profil",
)


def _is_likely_location(candidate: str) -> bool:
    lower = candidate.lower()
    if any(kw in lower for kw in ("domicile", "pourvoir", "gérer", "présentiel",
                                   "télétravail", "distanciel")):
        return False
    first_word = candidate.split()[0].lower() if candidate.split() else ""
    if first_word in _NON_LOCATION_WORDS:
        return False
    if first_word in _TITLE_LIKE_STARTS:
        return False
    if any(lower.startswith(w) for w in _NON_GEO_CONTENT):
        return False
    if len(candidate.split()) == 1 and first_word in ("en", "à", "au", "aux", "le", "la", "les", "des"):
        return False
    words = set(candidate.lower().split())
    if words & _NON_CITY_WORDS:
        return False
    lower = candidate.lower()
    if lower.startswith("vous avez"):
        return False
    if any(kw in lower for kw in ("capable de", "sensible aux", "relationnel",
                                   "protection des données")):
        return False
    word_count = len(candidate.split())
    if word_count > 8 and not _FRENCH_POSTAL_CODE.search(candidate):
        return False
    return True


def is_forbidden_title(text: str) -> bool:
    s = text.strip().rstrip(":").strip()
    if s in _FORBIDDEN_TITLES:
        return True
    lower = s.lower()
    for fb in _FORBIDDEN_TITLES:
        fb_lower = fb.lower().rstrip(".")
        if lower == fb_lower or lower.startswith(fb_lower):
            return True
    return False


def has_french_postal_code(text: str) -> bool:
    return bool(_FRENCH_POSTAL_CODE.search(text))


def is_probable_hiring_location(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if _POSTAL_CODE_FIRST.match(s):
        return True
    if _DEPARTMENT_PATTERN.match(s):
        return True
    if _POSTAL_CODE_LINE.match(s):
        return True
    if _CITY_LIKE.match(s) and _is_likely_location(s):
        return True
    lower = s.lower()
    if any(lower.startswith(p) for p in ("situé", "localisation", "lieu",
                                          "poste basé", "ville")):
        suffix = re.sub(r"^(?:situ[ée]\s+(?:a|à)\s+|lieu\s+du\s+poste\s*:?\s*"
                        r"|localisation\s*:?\s*|ville\s*:?\s*|poste\s+bas[ée]\s+(?:a|à|sur)\s+)",
                        "", s, flags=re.IGNORECASE).strip()
        if suffix and not re.match(r"\d", suffix) and _is_likely_location(suffix):
            return True
    return False


def normalize_salary(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^[Rr][ée]mun[eé]ration\s*:\s*", "", s).strip()
    s = re.sub(r"^(?:a|à)\s+partir\s+de\s+", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"^(?:minimum\s+)?garanti\s+", "", s, flags=re.IGNORECASE).strip()
    return s


def extract_location_after_marker(lines: list[str]) -> list[str]:
    results: list[str] = []
    markers_lower = {"lieu", "localisation", "ville", "région"}
    for i, line in enumerate(lines):
        lower = line.strip().lower().rstrip(":").strip()
        if lower in markers_lower and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and is_probable_hiring_location(next_line):
                results.append(next_line)
    return deduplicate_keep_order(results)


_FORBIDDEN_CONTENT = frozenset({
    "cdi", "cdd", "stage", "freelance", "alternance", "intérim",
    "les missions du poste", "présentation du poste",
    "rémunération", "description de la structure",
    "avantages du poste", "le profil recherché",
    "l'entreprise", "salaire", "type de poste",
    "services aux entreprises",
    "assistante dentaire dédiée",
    "personnel administratif compétent",
    "flux de patients important",
    "plateau technique moderne",
    "le profil recherché",
})

_DEPARTMENT_PATTERN = re.compile(
    r"^[A-Za-zÀ-ÿ\-]+(?:\s*-\s*\d{2,3})$"
)


def extract_hiring_locations(text: str) -> list[str]:
    results: list[str] = []

    for pat in LOCATION_PREFIX_PATTERNS:
        for m in pat.finditer(text):
            candidate = m.group(1).strip()
            if not candidate or re.match(r"\d", candidate):
                continue
            if _is_likely_location(candidate):
                results.append(candidate)

    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        lower_line = line.lower()

        if len(line.split()) > 8 and not _FRENCH_POSTAL_CODE.search(line):
            continue
        if lower_line.startswith("vous avez"):
            continue
        if any(kw in lower_line for kw in ("capable de", "sensible aux",
                                            "relationnel")):
            continue

        if _POSTAL_CODE_FIRST.match(line):
            results.append(line)
            continue
        if _DEPARTMENT_PATTERN.match(line):
            results.append(line)
            continue
        if _POSTAL_CODE_LINE.match(line):
            results.append(line)
            continue
        if _CITY_LIKE.match(line):
            if (not _is_likely_location(line)
                    or is_probable_company_name(line)
                    or is_sector_line(line)):
                continue
            results.append(line)

    return deduplicate_keep_order(results)


def normalize_phone_number(raw: str) -> str | None:
    s = raw.replace("O", "0").replace("o", "0")
    digits = re.sub(r"[^\d+]", "", s)
    if not digits:
        return None
    for fmt_len, expected_prefix in [(10, "0"), (11, "+33"), (12, "0033")]:
        if len(digits) == fmt_len:
            if digits.startswith("0"):
                pairs = " ".join(digits[i:i+2] for i in range(0, 10, 2))
                return pairs
            elif digits.startswith("33") and len(digits) == 11:
                pairs = " ".join(("0" + digits[2:][i:i+2]) for i in range(0, 9, 2))
                return pairs
            elif digits.startswith("0033") and len(digits) == 12:
                pairs = " ".join(("0" + digits[4:][i:i+2]) for i in range(0, 9, 2))
                return pairs
    return None


_CONTACT_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"https?://[^\s,;)]+"),
    re.compile(r"(?:\bcontact\b|recruteur|à contacter|interlocuteur)\s*:?\s*(.{3,60}?)(?:\.|,|$)", re.IGNORECASE),
]


def extract_contacts(text: str) -> list[str]:
    results: list[str] = []
    for pat in _CONTACT_PATTERNS:
        for m in pat.finditer(text):
            candidate = m.group(1).strip() if m.lastindex else m.group(0).strip()
            if candidate:
                results.append(candidate)

    phone_candidates = re.findall(
        r"(?:\b[0O])[1-9Oo](?:[\s.-]*[0-9Oo]){7,9}",
        text,
    )
    for raw in phone_candidates:
        normalized = normalize_phone_number(raw)
        if normalized:
            results.append(normalized)

    return deduplicate_keep_order(results)


extract_required_skills = extract_skills
