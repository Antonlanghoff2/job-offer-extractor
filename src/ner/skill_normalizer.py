# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Normalisation des compétences extraites par le NER.

Ce module sert de couche commune à l'ensemble du projet. Il transforme une
chaîne libre en nom canonique stable, puis regroupe les variantes proches
autour d'une compétence unique.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional

from .skill_dictionary import ALIAS_LIST, SKILL_ALIAS_INDEX, SKILL_DICTIONARY, build_alias_pattern, normalize_skill_lookup
from .skill_similarity import should_merge_skills


_VERSION_SUFFIX_RE = re.compile(r"^(.+?)\s+\d+(?:\.\d+)*(?:\s*[a-z])?$")
_GENERIC_PREFIXES = (
    "programmation ",
    "developpement ",
    "développement ",
    "coder en ",
    "maitrise de ",
    "maîtrise de ",
    "notions de ",
    "competence en ",
    "compétence en ",
)


def _clean_original_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" -–—:;,.")
    return text


def _title_case_preserving_acronyms(text: str) -> str:
    if not text:
        return ""
    if text.isupper() and len(text) <= 5:
        return text
    words = []
    for word in text.split():
        if word.isupper() and len(word) <= 5:
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:].lower())
    return " ".join(words)


def _direct_alias_match(value: str) -> Optional[str]:
    normalized = normalize_skill_lookup(value)
    if not normalized:
        return None
    canonical = SKILL_ALIAS_INDEX.get(normalized)
    if canonical:
        return canonical
    version_match = _VERSION_SUFFIX_RE.match(normalized)
    if version_match:
        base = normalize_skill_lookup(version_match.group(1))
        canonical = SKILL_ALIAS_INDEX.get(base)
        if canonical:
            return canonical
    for prefix in _GENERIC_PREFIXES:
        if normalized.startswith(prefix):
            candidate = normalize_skill_lookup(normalized[len(prefix):])
            canonical = SKILL_ALIAS_INDEX.get(candidate)
            if canonical:
                return canonical
    for alias in ALIAS_LIST:
        pattern = build_alias_pattern(alias)
        if not pattern:
            continue
        if re.search(pattern, normalized):
            canonical = SKILL_ALIAS_INDEX[alias]
            if canonical:
                return canonical
    return None


def canonicalize_skill_name(value: object) -> str:
    """Retourne le nom canonique d'une compétence.

    Si la compétence n'est pas reconnue, la fonction conserve le texte d'origine
    nettoyé et le remet dans une casse lisible.
    """

    cleaned = _clean_original_text(value)
    if not cleaned:
        return ""
    canonical = _direct_alias_match(cleaned)
    if canonical:
        return canonical
    return _title_case_preserving_acronyms(cleaned)


def normalize_skill_name(value: object) -> str:
    """Alias public historique pour la normalisation canonique."""

    return canonicalize_skill_name(value)


def normalize_skill_names(values: Iterable[object]) -> List[str]:
    """Normalise et déduplique une liste de compétences."""

    result: List[str] = []
    seen = set()
    for value in values:
        canonical = canonicalize_skill_name(value)
        key = normalize_skill_lookup(canonical)
        if not canonical or key in seen:
            continue
        seen.add(key)
        result.append(canonical)
    return result


def group_skill_variants(values: Iterable[object]) -> "OrderedDict[str, List[str]]":
    """Regroupe les variantes d'une liste de compétences autour d'un canonique."""

    groups: "OrderedDict[str, List[str]]" = OrderedDict()
    canonical_order: List[str] = []
    unresolved: List[str] = []

    for value in values:
        cleaned = _clean_original_text(value)
        if not cleaned:
            continue
        canonical = canonicalize_skill_name(cleaned)
        if not canonical:
            continue
        normalized_canonical = normalize_skill_lookup(canonical)
        if canonical in SKILL_DICTIONARY or normalized_canonical in SKILL_ALIAS_INDEX:
            groups.setdefault(canonical, [])
            if cleaned not in groups[canonical]:
                groups[canonical].append(cleaned)
            if canonical not in canonical_order:
                canonical_order.append(canonical)
        else:
            unresolved.append(cleaned)

    for variant in unresolved:
        matched = None
        for canonical in canonical_order:
            if should_merge_skills(variant, canonical):
                matched = canonical
                break
        if matched is None:
            matched = _title_case_preserving_acronyms(variant)
            if matched not in groups:
                groups[matched] = []
                canonical_order.append(matched)
        if variant not in groups[matched]:
            groups[matched].append(variant)

    return groups

