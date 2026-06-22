# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Normalisation et fusion des compétences extraites.

Ce module est responsable de la fusion des doublons, de la résolution
des synonymes et de l'application des priorités entre types d'extraction.

Ordre de priorité : ``explicit`` > ``semantic`` > ``implicit``.

Lorsqu'une même compétence est détectée par plusieurs niveaux du
pipeline, la version avec le score de confiance le plus élevé et le
type d'extraction le plus fort est conservée.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, List, Optional

from src.ner.skill_normalizer import canonicalize_skill_name

from .models import ExtractedSkill

_EXTRACTION_PRIORITY = {"explicit": 3, "semantic": 2, "implicit": 1}

_GENERIC_SKILLS = frozenset({
    "développement", "developpement", "analyse", "data", "informatique",
    "qualité", "qualite", "gestion", "management", "communication",
    "travail", "équipe", "equipe", "projet", "client", "service",
})

_SHORT_VALID_SKILLS = frozenset({
    "sql", "aws", "api", "git", "css", "html", "xml", "json", "yaml",
    "rest", "soap", "crm", "erp", "bi", "ui", "ux", "ci", "cd",
})

_VERB_TO_NOUN = {
    "développer": "Développement",
    "developper": "Développement",
    "concevoir": "Conception",
    "analyser": "Analyse",
    "gérer": "Gestion",
    "gerer": "Gestion",
    "administrer": "Administration",
    "piloter": "Pilotage",
    "maintenir": "Maintenance",
    "déployer": "Déploiement",
    "deployer": "Déploiement",
    "superviser": "Supervision",
    "rédiger": "Rédaction",
    "rediger": "Rédaction",
    "former": "Formation",
    "coordonner": "Coordination",
    "optimiser": "Optimisation",
    "automatiser": "Automatisation",
    "tester": "Tests",
    "intégrer": "Intégration",
    "integrer": "Intégration",
    "surveiller": "Monitoring",
    "mettre en place": "Mise en place",
}


def _normalize_key(name: str) -> str:
    """Retourne une clé de normalisation pour la déduplication."""

    return canonicalize_skill_name(name).lower()


def _is_too_generic(name: str) -> bool:
    """Vérifie si une compétence est trop générique pour être retenue."""

    cleaned = name.lower().strip()
    if len(cleaned) <= 3:
        if cleaned in _SHORT_VALID_SKILLS:
            return False
        if cleaned.isupper() and len(cleaned) >= 2:
            return False
        return True
    if cleaned in _GENERIC_SKILLS:
        return True
    words = cleaned.split()
    if len(words) == 1 and cleaned in _GENERIC_SKILLS:
        return True
    return False


def normalize_phrase_to_skill(phrase: str) -> Optional[str]:
    """Transforme une phrase verbale en compétence nominale.

    Exemples :
    - « Développer des modèles prédictifs » → « Développement de modèles prédictifs »
    - « Concevoir l'ingénierie de formation » → « Ingénierie de formation »
    - « Analyser les données » → « Analyse de données »

    Args:
        phrase: Phrase verbale à transformer.

    Returns:
        Compétence nominale ou None si la phrase ne peut être transformée.
    """

    if not phrase or len(phrase.strip()) < 5:
        return None

    cleaned = re.sub(r"\s+", " ", phrase).strip()
    cleaned_lower = cleaned.lower()

    for verb, noun in _VERB_TO_NOUN.items():
        if cleaned_lower.startswith(verb + " ") or cleaned_lower.startswith(verb + "s "):
            rest = cleaned[len(verb):].strip()
            rest = re.sub(r"^(des?|les?|un|une|des)\s+", "", rest, flags=re.IGNORECASE)
            if rest and len(rest) > 2:
                if rest.lower().startswith("de "):
                    return f"{noun} {rest}"
                return f"{noun} de {rest}"

    return None


def merge_skills(skills: List[ExtractedSkill]) -> List[ExtractedSkill]:
    """Fusionne les doublons et conserve le meilleur score.

    Parcourt la liste des compétences extraites et regroupe celles
    qui correspondent au même nom canonique. Pour chaque groupe,
    la version avec la priorité d'extraction la plus haute et le
    score de confiance le plus élevé est conservée.

    Les phrases verbales sont transformées en compétences nominales.
    Les compétences trop génériques sont filtrées.

    Args:
        skills: Liste de compétences potentiellement dupliquées.

    Returns:
        Liste fusionnée et triée par confiance décroissante.
    """

    merged: Dict[str, ExtractedSkill] = {}

    for skill in skills:
        if skill.negated:
            continue

        normalized_name = skill.canonical_name
        if skill.extraction_type == "explicit" and " " in normalized_name:
            phrase_normalized = normalize_phrase_to_skill(normalized_name)
            if phrase_normalized:
                normalized_name = phrase_normalized

        if _is_too_generic(normalized_name):
            continue

        key = _normalize_key(normalized_name)
        if not key:
            continue

        if normalized_name != skill.canonical_name:
            skill = ExtractedSkill(
                canonical_name=normalized_name,
                raw_text=skill.raw_text,
                source_sentence=skill.source_sentence,
                extraction_type=skill.extraction_type,
                confidence=skill.confidence,
                category=skill.category,
                optional=skill.optional,
                negated=skill.negated,
            )

        existing = merged.get(key)
        if existing is None:
            merged[key] = skill
            continue
        existing_priority = _EXTRACTION_PRIORITY.get(existing.extraction_type, 0)
        new_priority = _EXTRACTION_PRIORITY.get(skill.extraction_type, 0)
        if new_priority > existing_priority:
            merged[key] = skill
        elif new_priority == existing_priority and skill.confidence > existing.confidence:
            merged[key] = skill

    sorted_skills = sorted(
        merged.values(),
        key=lambda s: (-_EXTRACTION_PRIORITY.get(s.extraction_type, 0), -s.confidence, s.canonical_name),
    )
    return sorted_skills


def deduplicate_by_canonical(skills: List[ExtractedSkill]) -> List[ExtractedSkill]:
    """Déduplique les compétences par nom canonique.

    Conserve la première occurrence de chaque nom canonique.

    Args:
        skills: Liste de compétences à dédupliquer.

    Returns:
        Liste dédupliquée dans l'ordre d'origine.
    """

    seen: set = set()
    result: List[ExtractedSkill] = []
    for skill in skills:
        key = _normalize_key(skill.canonical_name)
        if key and key not in seen:
            seen.add(key)
            result.append(skill)
    return result
