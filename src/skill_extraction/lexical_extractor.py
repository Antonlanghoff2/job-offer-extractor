# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Extraction lexicale de compétences explicites.

Niveau 1 du pipeline hybride. Ce module détecte les compétences
explicitement mentionnées dans un texte à partir :

- du dictionnaire NER centralisé du projet ;
- d'expressions régulières ;
- de la liste ``KNOWN_SKILLS`` historique.

L'extraction est déterministe et conservatrice : elle ne retient que
les compétences reconnues par le référentiel.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from src.extractors import KNOWN_SKILLS
from src.ner.skill_dictionary import SKILL_DICTIONARY, normalize_skill_lookup
from src.ner.skill_entity_extractor import extract_skill_entities
from src.ner.skill_normalizer import canonicalize_skill_name

from .models import ExtractedSkill

logger = logging.getLogger(__name__)

ENABLE_LEXICAL_EXTRACTION = os.getenv("ENABLE_LEXICAL_EXTRACTION", "true").lower() in ("true", "1", "yes")

_NEGATION_PREFIXES = (
    "aucune connaissance de",
    "aucune expérience en",
    "pas de connaissance en",
    "pas d'expérience en",
    "non requis",
    "non requise",
    "non nécessaire",
    "non nécessaire",
    "pas nécessaire",
    "pas obligatoire",
    "inutile de connaître",
    "inutile de maitriser",
    "inutile de maîtriser",
)

_OPTIONAL_MARKERS = (
    "serait un plus",
    "est un plus",
    "souhaitable",
    "souhaitée",
    "souhaité",
    "idéalement",
    "de préférence",
    "un atout",
    "bonus",
    "apprécié",
    "appréciée",
)

_ACTION_VERBS = (
    "maîtriser", "maitriser", "connaître", "connaitre", "développer",
    "concevoir", "déployer", "administrer", "analyser", "piloter",
    "maintenir", "automatiser", "superviser", "utiliser", "programmer",
    "coder", "implémenter", "mettre en place", "gérer",
)

_KNOWN_SKILLS_LOWER = {skill.lower(): skill for skill in KNOWN_SKILLS}

_KNOWN_SKILLS_PATTERN = re.compile(
    r"|".join(re.escape(skill) for skill in sorted(KNOWN_SKILLS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _is_negated(sentence: str, match_start: int) -> bool:
    """Vérifie si la compétence est dans un contexte de négation."""

    prefix = sentence[max(0, match_start - 40):match_start].lower()
    return any(neg in prefix for neg in _NEGATION_PREFIXES)


def _is_optional(sentence: str, match_end: int) -> bool:
    """Vérifie si la compétence est souhaitée mais non requise."""

    suffix = sentence[match_end:match_end + 40].lower()
    return any(marker in suffix for marker in _OPTIONAL_MARKERS)


def _find_sentence_for_position(text: str, position: int) -> str:
    """Retourne la phrase contenant la position donnée."""

    start = text.rfind(".", 0, position)
    start = text.rfind("\n", 0, position) if start == -1 else max(start, text.rfind("\n", 0, position))
    start = max(start + 1, 0) if start >= 0 else 0
    end = text.find(".", position)
    end_nl = text.find("\n", position)
    if end == -1:
        end = len(text)
    if end_nl != -1 and end_nl < end:
        end = end_nl
    else:
        end = min(end + 1, len(text))
    return text[start:end].strip()


def extract_explicit_skills(text: str) -> List[ExtractedSkill]:
    """Détecte les compétences explicites dans un texte.

    Parcourt le texte à la recherche de compétences reconnues par le
    dictionnaire NER et la liste ``KNOWN_SKILLS``. Chaque détection
    conserve la phrase source, le type ``explicit`` et un score de
    confiance de 1.0.

    Args:
        text: Texte brut de l'offre d'emploi.

    Returns:
        Liste de compétences explicites détectées.
    """

    if not text or not ENABLE_LEXICAL_EXTRACTION:
        return []

    results: Dict[str, ExtractedSkill] = {}

    for entity in extract_skill_entities(text, source="explicite"):
        sentence = _find_sentence_for_position(text, text.lower().find(entity.text.lower()))
        negated = _is_negated(text, text.lower().find(entity.text.lower()))
        optional = _is_optional(text, text.lower().find(entity.text.lower()) + len(entity.text))
        key = entity.canonical_name.lower()
        if key not in results:
            results[key] = ExtractedSkill(
                canonical_name=entity.canonical_name,
                raw_text=entity.text,
                source_sentence=sentence,
                extraction_type="explicit",
                confidence=1.0,
                category=entity.category,
                optional=optional,
                negated=negated,
            )

    for match in _KNOWN_SKILLS_PATTERN.finditer(text):
        raw = match.group(0)
        canonical = _KNOWN_SKILLS_LOWER.get(raw.lower(), raw)
        canonical = canonicalize_skill_name(canonical)
        if not canonical:
            continue
        sentence = _find_sentence_for_position(text, match.start())
        negated = _is_negated(text, match.start())
        optional = _is_optional(text, match.end())
        key = canonical.lower()
        if key not in results:
            results[key] = ExtractedSkill(
                canonical_name=canonical,
                raw_text=raw,
                source_sentence=sentence,
                extraction_type="explicit",
                confidence=1.0,
                category=None,
                optional=optional,
                negated=negated,
            )

    return list(results.values())
