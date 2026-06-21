# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Extraction légère d'entités compétences à partir de texte libre.

Cette implémentation repose d'abord sur le dictionnaire métier du projet.
Elle peut être remplacée plus tard par un moteur spaCy, CamemBERT ou
Sentence-BERT sans changer l'interface fonctionnelle.
"""

from __future__ import annotations

from collections import OrderedDict
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .skill_dictionary import ALIAS_LIST, SKILL_ALIAS_INDEX, SKILL_DICTIONARY, build_alias_pattern, normalize_skill_lookup
from .skill_normalizer import canonicalize_skill_name, group_skill_variants
from .skill_similarity import skill_similarity_score


@dataclass
class SkillEntity:
    """Entité de compétence détectée dans un texte."""

    text: str
    canonical_name: str
    alias: str
    category: Optional[str]
    confidence: float
    source: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "text": self.text,
            "canonical_name": self.canonical_name,
            "alias": self.alias,
            "category": self.category,
            "confidence": self.confidence,
            "source": self.source,
        }


def _canonical_category(canonical_name: str) -> Optional[str]:
    spec = SKILL_DICTIONARY.get(canonical_name)
    if not spec:
        return None
    category = spec.get("category")
    return str(category) if category else None


def _candidate_sentences(text: str) -> List[str]:
    lines = [part.strip() for part in text.replace("\r", "\n").split("\n") if part.strip()]
    fragments: List[str] = []
    for line in lines:
        fragments.extend([part.strip() for part in line.replace(";", ",").replace("|", ",").split(",") if part.strip()])
    return fragments or [text.strip()]


def _confidence_for_match(alias: str, canonical_name: str, fragment: str) -> float:
    normalized_alias = normalize_skill_lookup(alias)
    normalized_fragment = normalize_skill_lookup(fragment)
    if normalized_alias == normalized_fragment:
        return 0.98
    if re.search(build_alias_pattern(alias), normalized_fragment):
        return 0.92
    return round(max(0.55, skill_similarity_score(alias, fragment)), 2)


def extract_skill_entities(text: str, source: str = "texte libre") -> List[SkillEntity]:
    """Détecte les compétences présentes dans un texte libre.

    La détection repose sur un balayage du dictionnaire métier. La fonction
    renvoie des entités déjà normalisées, mais conserve le texte source pour
    faciliter le debug et l'explicabilité.
    """

    if not text:
        return []

    normalized = normalize_skill_lookup(text)
    entities: List[SkillEntity] = []
    seen = set()

    for alias in ALIAS_LIST:
        canonical = SKILL_ALIAS_INDEX[alias]
        pattern = build_alias_pattern(alias)
        if not pattern:
            continue
        if not re.search(pattern, normalized):
            continue
        if normalize_skill_lookup(canonical) in seen:
            continue
        confidence = _confidence_for_match(alias, canonical, normalized)
        entities.append(
            SkillEntity(
                text=canonical,
                canonical_name=canonical,
                alias=alias,
                category=_canonical_category(canonical),
                confidence=confidence,
                source=source,
            )
        )
        seen.add(normalize_skill_lookup(canonical))

    # On ajoute les variantes reconnues implicitement via la normalisation.
    for fragment in _candidate_sentences(text):
        canonical = canonicalize_skill_name(fragment)
        if not canonical:
            continue
        normalized_canonical = normalize_skill_lookup(canonical)
        if normalized_canonical in seen:
            continue
        if canonical in SKILL_DICTIONARY:
            entities.append(
                SkillEntity(
                    text=canonical,
                    canonical_name=canonical,
                    alias=normalize_skill_lookup(fragment),
                    category=_canonical_category(canonical),
                    confidence=0.84,
                    source=source,
                )
            )
            seen.add(normalized_canonical)

    return entities


def extract_skill_names(text: str, source: str = "texte libre") -> List[str]:
    """Retourne les noms canoniques détectés dans un texte."""

    return [entity.canonical_name for entity in extract_skill_entities(text, source=source)]


def group_skill_entities(entities: Iterable[SkillEntity]) -> "OrderedDict[str, List[str]]":
    """Regroupe les entités détectées par compétence canonique."""

    values = [entity.alias or entity.text for entity in entities]
    return group_skill_variants(values)

