# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Extraction de diplôme, salaire et télétravail depuis le texte des offres.

Ce module fournit des extracteurs déterministes pour trois champs
qui ne sont pas toujours présents dans les données structurées France Travail
mais qui peuvent être déduits du texte de description.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


_DIPLOMA_LEVELS: Dict[str, int] = {
    "cap": 3, "bep": 3,
    "bac": 4,
    "bac +2": 5, "bac+2": 5, "bts": 5, "dut": 5, "deug": 5,
    "bac +3": 6, "bac+3": 6, "licence": 6, "bachelor": 6, "but": 6,
    "bac +4": 7, "bac+4": 7, "master 1": 7, "m1": 7,
    "bac +5": 8, "bac+5": 8, "master": 8, "master 2": 8, "m2": 8,
    "diplome d'ingenieur": 8, "diplôme d'ingénieur": 8, "ingenieur": 8,
    "doctorat": 10, "these": 10, "thèse": 10, "phd": 10,
}

_DIPLOMA_PATTERN = re.compile(
    r"(?:"
    r"(?:dipl[oô]me|titre|certification)\s+(?:de\s+)?(?:niveau\s+)?(?:bac\s*\+?\s*\d|cap|bep|bts|dut|but|licence|bachelor|master(?:\s*[12])?|doctorat|th[eè]se|ing[eé]nieur|rncp)"
    r"|(?:bac\s*\+?\s*\d)"
    r"|\b(?:cap|bep|bts|dut|but|licence|bachelor|master(?:\s*[12])?|doctorat|th[eè]se|ing[eé]nieur)\b"
    r"|titre\s+rncp"
    r")",
    re.IGNORECASE,
)

_NEGATION_DIPLOMA = re.compile(
    r"(?:aucun|pas de|non requis|non requise|non n[ée]cessaire|inutile|sans)\s+(?:dipl[oô]me|formation|bac|bts|master|licence)",
    re.IGNORECASE,
)

_SALARY_PATTERN = re.compile(
    r"(?:(\d[\d\s]{1,6}(?:[.,]\d+)?)\s*(?:à|-|et|/)\s*(\d[\d\s]{1,6}(?:[.,]\d+)?)|(\d[\d\s]{1,6}(?:[.,]\d+)?))"
    r"\s*(?:€|euros?|EUR|k€)?"
    r"(?:\s*(?:brut|net))?"
    r"(?:\s*(?:par\s+)?(?:mois|an|ann[ée]e|jour|heure|mois))?",
    re.IGNORECASE,
)

_SALARY_FULL_PATTERN = re.compile(
    r"(\d[\d\s]{1,6}(?:[.,]\d+)?)\s*(?:à|-|et)\s*(\d[\d\s]{1,6}(?:[.,]\d+)?)\s*"
    r"(?:€|euros?|EUR)?"
    r"(?:\s*(brut|net))?"
    r"(?:\s*(?:par\s+)?(mois|an|ann[ée]e|jour|heure))?",
    re.IGNORECASE,
)

_SALARY_SINGLE_PATTERN = re.compile(
    r"(?:à partir de|environ|)?\s*(\d[\d\s]{1,6}(?:[.,]\d+)?)\s*"
    r"(?:€|euros?|EUR|k€)?"
    r"(?:\s*(brut|net))?"
    r"(?:\s*(?:par\s+)?(mois|an|ann[ée]e|jour|heure))?",
    re.IGNORECASE,
)

_SALARY_DAY_PATTERN = re.compile(
    r"(\d[\d\s]{1,6}(?:[.,]\d+)?)\s*(?:€|euros?|EUR)\s*(?:par\s+)?jour",
    re.IGNORECASE,
)

_TELETRAVAIL_PATTERNS = [
    (re.compile(r"(?:100\s*%|full)\s*(?:teletravail|remote|distanciel)", re.IGNORECASE), "remote"),
    (re.compile(r"teletravail\s+(?:complet|total)", re.IGNORECASE), "remote"),
    (re.compile(r"full\s*remote", re.IGNORECASE), "remote"),
    (re.compile(r"(\d)\s*(?:jours?|j)\s*(?:de\s+)?(?:teletravail|t[ée]l[ée]travail)", re.IGNORECASE), "hybrid"),
    (re.compile(r"teletravail\s+(?:partiel|possible|accept[ée])", re.IGNORECASE), "hybrid"),
    (re.compile(r"(?:2|3)\s*jours?\s*/\s*semaine", re.IGNORECASE), "hybrid"),
    (re.compile(r"hybride", re.IGNORECASE), "hybrid"),
    (re.compile(r"(?:teletravail|remote)\s+occasionnel", re.IGNORECASE), "occasional"),
    (re.compile(r"aucun\s*(?:teletravail|t[ée]l[ée]travail)", re.IGNORECASE), "onsite"),
    (re.compile(r"(?:pas de|sans)\s*(?:teletravail|t[ée]l[ée]travail)", re.IGNORECASE), "onsite"),
    (re.compile(r"pr[ée]sentiel", re.IGNORECASE), "onsite"),
    (re.compile(r"(?:100\s*%|full)\s*(?:sur\s*site|presentiel)", re.IGNORECASE), "onsite"),
    (re.compile(r"entièrement\s+sur\s+site", re.IGNORECASE), "onsite"),
    (re.compile(r"sur\s+site", re.IGNORECASE), "onsite"),
    (re.compile(r"teletravail", re.IGNORECASE), "hybrid"),
    (re.compile(r"distanciel", re.IGNORECASE), "remote"),
    (re.compile(r"remote", re.IGNORECASE), "remote"),
]


def extract_diplomas_from_text(text: str) -> List[Dict[str, Any]]:
    """Extrait les diplômes mentionnés dans le texte d'une offre.

    Args:
        text: Texte brut de l'offre.

    Returns:
        Liste de dictionnaires avec label, level, required, source_sentence.
    """
    if not text:
        return []

    results: List[Dict[str, Any]] = []
    seen: set = set()

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])|(?<=\n)", text)

    for sentence in sentences:
        if _NEGATION_DIPLOMA.search(sentence):
            continue

        matches = _DIPLOMA_PATTERN.findall(sentence)
        for match_text in re.finditer(_DIPLOMA_PATTERN.pattern, sentence, re.IGNORECASE):
            raw = match_text.group(0).strip()
            key = raw.lower().strip()
            if key in seen:
                continue
            seen.add(key)

            level = _diploma_level(key)
            required = _is_diploma_required(sentence)

            results.append({
                "label": raw,
                "level": level,
                "required": required,
                "source_sentence": sentence.strip(),
                "confidence": 0.90 if required else 0.70,
            })

    return results


def _diploma_level(text: str) -> int:
    """Retourne le niveau CNP d'un diplôme."""
    normalized = text.lower().strip()
    for key, level in _DIPLOMA_LEVELS.items():
        if key in normalized:
            return level
    return 0


def _is_diploma_required(sentence: str) -> bool:
    """Détermine si le diplôme est obligatoire ou souhaité."""
    lower = sentence.lower()
    optional_markers = ("souhait", "apprécié", "atout", "bonus", "idéalement", "préférence", "serait un plus")
    if any(m in lower for m in optional_markers):
        return False
    required_markers = ("requis", "exigé", "exige", "obligatoire", "demandé", "demande", "minimum", "indispensable")
    if any(m in lower for m in required_markers):
        return True
    return True


def extract_salary_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extrait le salaire mentionné dans le texte d'une offre.

    Args:
        text: Texte brut de l'offre.

    Returns:
        Dictionnaire avec minimum, maximum, currency, period, gross, raw_text.
        None si aucun salaire trouvé.
    """
    if not text:
        return None

    match = _SALARY_FULL_PATTERN.search(text)
    if match:
        min_val = _parse_salary_number(match.group(1))
        max_val = _parse_salary_number(match.group(2))
        gross = match.group(3) is None or match.group(3).lower() != "net"
        period = _normalize_period(match.group(4))
        raw = match.group(0).strip()
        return {
            "minimum": min_val,
            "maximum": max_val,
            "currency": "EUR",
            "period": period,
            "gross": gross,
            "raw_text": raw,
        }

    match = _SALARY_DAY_PATTERN.search(text)
    if match:
        val = _parse_salary_number(match.group(1))
        if val and val >= 50:
            raw = match.group(0).strip()
            return {
                "minimum": val,
                "maximum": val,
                "currency": "EUR",
                "period": "day",
                "gross": True,
                "raw_text": raw,
            }

    match = _SALARY_SINGLE_PATTERN.search(text)
    if match:
        val = _parse_salary_number(match.group(1))
        if val and val >= 500:
            gross = match.group(2) is None or match.group(2).lower() != "net"
            period = _normalize_period(match.group(3))
            raw = match.group(0).strip()
            return {
                "minimum": val,
                "maximum": val,
                "currency": "EUR",
                "period": period,
                "gross": gross,
                "raw_text": raw,
            }

    return None


def _parse_salary_number(text: str) -> Optional[int]:
    """Parse un nombre de salaire en entier."""
    if not text:
        return None
    cleaned = text.replace(" ", "").replace(",", ".")
    try:
        val = int(float(cleaned))
        if val < 100:
            return val * 1000
        return val
    except (ValueError, TypeError):
        return None


def _normalize_period(text: Optional[str]) -> str:
    """Normalise la période du salaire."""
    if not text:
        return "year"
    lower = text.lower()
    if "jour" in lower or "journée" in lower:
        return "day"
    if "mois" in lower:
        return "month"
    if "heure" in lower:
        return "hour"
    return "year"


def extract_teletravail_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extrait le mode de télétravail depuis le texte d'une offre.

    Args:
        text: Texte brut de l'offre.

    Returns:
        Dictionnaire avec mode, days_per_week, raw_text, confidence.
        None si aucune information trouvée.
    """
    if not text:
        return None

    for pattern, mode in _TELETRAVAIL_PATTERNS:
        match = pattern.search(text)
        if match:
            raw = match.group(0).strip()
            days = None
            if match.lastindex and match.lastindex >= 1:
                try:
                    days = int(match.group(1))
                except (ValueError, IndexError):
                    pass
            return {
                "mode": mode,
                "days_per_week": days,
                "raw_text": raw,
                "confidence": 0.95,
            }

    return None
