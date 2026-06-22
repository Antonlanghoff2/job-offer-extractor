# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Pipeline hybride d'extraction de compétences.

Ce module orchestre les niveaux d'extraction :

1. **Extraction lexicale** — détection des compétences explicites.
2. **Extraction de candidats** — extraction d'expressions candidates.
3. **Rapprochement sémantique** — comparaison avec le référentiel.
4. **Extraction implicite** — déduction de compétences depuis les missions.
5. **Normalisation** — fusion des doublons et tri.

La fonction principale ``extract_skills_from_offer`` retourne une liste
de ``ExtractedSkill`` triée par priorité et confiance.

La fonction ``extract_skills_categorized`` retourne les compétences
séparées par type d'extraction : explicite, sémantique, implicite.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from .candidate_extractor import extract_candidates
from .implicit_extractor import ImplicitExtractionDebug, extract_implicit_skills
from .lexical_extractor import extract_explicit_skills
from .models import ExtractedSkill
from .savoir_faire_extractor import extract_savoir_faire
from .semantic_matcher import match_candidates_to_referential
from .skill_normalizer import merge_skills

logger = logging.getLogger(__name__)

ENABLE_SEMANTIC_EXTRACTION = os.getenv("ENABLE_SEMANTIC_EXTRACTION", "true").lower() in ("true", "1", "yes")
ENABLE_IMPLICIT_EXTRACTION = os.getenv("ENABLE_IMPLICIT_EXTRACTION", "true").lower() in ("true", "1", "yes")
ENABLE_SAVOIR_FAIRE_EXTRACTION = os.getenv("ENABLE_SAVOIR_FAIRE_EXTRACTION", "true").lower() in ("true", "1", "yes")
DEBUG_SKILL_EXTRACTION = os.getenv("DEBUG_SKILL_EXTRACTION", "false").lower() in ("true", "1", "yes")


def extract_skills_from_offer(
    text: str,
    *,
    structured_competences: Optional[List[str]] = None,
    debug: bool = False,
) -> List[ExtractedSkill]:
    """Pipeline complet d'extraction de compétences depuis une offre.

    Exécute les niveaux d'extraction dans l'ordre :

    1. Compétences structurées de l'API France Travail (si fournies).
    2. Détection des compétences explicites par le dictionnaire NER.
    3. Extraction des savoir-faire depuis les phrases verbales.
    4. Extraction d'expressions candidates depuis le texte brut.
    5. Rapprochement sémantique des candidats avec le référentiel.
    6. Extraction implicite depuis les descriptions de missions.
    7. Fusion des doublons et application des priorités.

    Args:
        text: Texte brut complet de l'offre d'emploi.
        structured_competences: Compétences structurées de l'API France Travail.
        debug: Si True, retourne des informations de debug dans les résultats.

    Returns:
        Liste de compétences extraites, triées par priorité et confiance.

    Example:
        >>> skills = extract_skills_from_offer("Maîtrise de Python et Docker requis.")
        >>> [s.canonical_name for s in skills]
        ['Python', 'Docker']
    """

    if not text or not text.strip():
        return []

    logger.debug("Début de l'extraction hybride sur %d caractères.", len(text))

    all_skills: List[ExtractedSkill] = []

    if structured_competences:
        for comp in structured_competences:
            if comp and comp.strip():
                all_skills.append(ExtractedSkill(
                    canonical_name=comp.strip(),
                    raw_text=comp.strip(),
                    source_sentence="(API France Travail)",
                    extraction_type="explicit",
                    confidence=1.0,
                    category=None,
                    optional=False,
                    negated=False,
                ))
        logger.debug("Compétences structurées ajoutées: %d", len(structured_competences))

    explicit_skills = extract_explicit_skills(text)
    logger.debug("Compétences explicites détectées: %d", len(explicit_skills))
    all_skills.extend(explicit_skills)

    if ENABLE_SAVOIR_FAIRE_EXTRACTION:
        savoir_faire_skills = _extract_savoir_faire_as_skills(text)
        logger.debug("Savoir-faire détectés: %d", len(savoir_faire_skills))
        all_skills.extend(savoir_faire_skills)

    if ENABLE_SEMANTIC_EXTRACTION:
        candidates = extract_candidates(text)
        logger.debug("Candidats extraits: %d", len(candidates))

        explicit_names = {skill.canonical_name.lower() for skill in all_skills}
        filtered_candidates = [
            (candidate, sentence)
            for candidate, sentence in candidates
            if candidate.lower() not in explicit_names
        ]

        semantic_skills = match_candidates_to_referential(filtered_candidates)
        logger.debug("Compétences sémantiques détectées: %d", len(semantic_skills))
        all_skills.extend(semantic_skills)

    if ENABLE_IMPLICIT_EXTRACTION:
        explicit_names_set = {skill.canonical_name.lower() for skill in all_skills}
        implicit_skills, implicit_debug = extract_implicit_skills(
            text,
            explicit_skills=explicit_names_set,
            debug=debug or DEBUG_SKILL_EXTRACTION,
        )
        logger.debug("Compétences implicites détectées: %d", len(implicit_skills))
        all_skills.extend(implicit_skills)

    merged = merge_skills(all_skills)
    logger.debug("Compétences après fusion: %d", len(merged))

    if debug or DEBUG_SKILL_EXTRACTION:
        logger.info("Debug extraction: %d compétences finales pour %d caractères", len(merged), len(text))
        for skill in merged:
            logger.info("  - %s (type=%s, conf=%.2f) <- %r", skill.canonical_name, skill.extraction_type, skill.confidence, skill.raw_text)

    return merged


def extract_skills_categorized(
    text: str,
    *,
    structured_competences: Optional[List[str]] = None,
    debug: bool = False,
) -> Dict[str, List[ExtractedSkill]]:
    """Extrait les compétences et les sépare par type d'extraction.

    Cette fonction exécute le pipeline complet et retourne les compétences
    séparées en trois catégories : explicite, sémantique, implicite.

    Args:
        text: Texte brut complet de l'offre d'emploi.
        structured_competences: Compétences structurées de l'API France Travail.
        debug: Si True, inclut les informations de debug.

    Returns:
        Dictionnaire avec les clés ``competences_explicit``,
        ``competences_semantic``, ``competences_implicit``.

    Example:
        >>> result = extract_skills_categorized("Python requis. Vous déploierez les modèles.")
        >>> len(result["competences_explicit"]) > 0
        True
    """

    if not text or not text.strip():
        return {
            "competences_explicit": [],
            "competences_semantic": [],
            "competences_implicit": [],
        }

    explicit_skills: List[ExtractedSkill] = []
    semantic_skills: List[ExtractedSkill] = []
    implicit_skills: List[ExtractedSkill] = []
    debug_data: Dict[str, Any] = {}

    if structured_competences:
        for comp in structured_competences:
            if comp and comp.strip():
                explicit_skills.append(ExtractedSkill(
                    canonical_name=comp.strip(),
                    raw_text=comp.strip(),
                    source_sentence="(API France Travail)",
                    extraction_type="explicit",
                    confidence=1.0,
                    category=None,
                    optional=False,
                    negated=False,
                ))

    extracted_explicit = extract_explicit_skills(text)
    explicit_skills.extend(extracted_explicit)

    if ENABLE_SAVOIR_FAIRE_EXTRACTION:
        savoir_faire = _extract_savoir_faire_as_skills(text)
        semantic_skills.extend(savoir_faire)

    if ENABLE_SEMANTIC_EXTRACTION:
        candidates = extract_candidates(text)
        explicit_names = {s.canonical_name.lower() for s in explicit_skills}
        filtered_candidates = [
            (c, s) for c, s in candidates if c.lower() not in explicit_names
        ]
        semantic = match_candidates_to_referential(filtered_candidates)
        semantic_skills.extend(semantic)

    if ENABLE_IMPLICIT_EXTRACTION:
        all_explicit_names = {s.canonical_name.lower() for s in explicit_skills}
        all_explicit_names.update(s.canonical_name.lower() for s in semantic_skills)

        implicit, implicit_debug = extract_implicit_skills(
            text,
            explicit_skills=all_explicit_names,
            debug=debug or DEBUG_SKILL_EXTRACTION,
        )
        implicit_skills.extend(implicit)
        if debug:
            debug_data["implicit_debug"] = [
                {
                    "sentence": d.sentence,
                    "is_mission": d.is_mission,
                    "is_negated": d.is_negated,
                    "is_generic": d.is_generic,
                    "accepted": d.accepted,
                    "rejected": d.rejected,
                }
                for d in implicit_debug
            ]

    explicit_merged = merge_skills(explicit_skills)
    semantic_merged = merge_skills(semantic_skills)
    implicit_merged = merge_skills(implicit_skills)

    result = {
        "competences_explicit": explicit_merged,
        "competences_semantic": semantic_merged,
        "competences_implicit": implicit_merged,
    }

    if debug:
        result["debug"] = debug_data

    return result


def extract_skills_as_dicts(text: str) -> List[Dict[str, object]]:
    """Extrait les compétences et retourne une liste de dictionnaires.

    Args:
        text: Texte brut de l'offre.

    Returns:
        Liste de dictionnaires JSON-compatibles.
    """

    return [skill.to_dict() for skill in extract_skills_from_offer(text)]


def extract_skill_names(text: str) -> List[str]:
    """Extrait uniquement les noms canoniques des compétences.

    Args:
        text: Texte brut de l'offre.

    Returns:
        Liste de noms canoniques dédupliqués.
    """

    return [skill.canonical_name for skill in extract_skills_from_offer(text)]


def _extract_savoir_faire_as_skills(text: str) -> List[ExtractedSkill]:
    """Extrait les savoir-faire et les convertit en ExtractedSkill."""

    savoir_faire = extract_savoir_faire(text)
    results: List[ExtractedSkill] = []

    for canonical_name, raw_text, source_sentence in savoir_faire:
        results.append(ExtractedSkill(
            canonical_name=canonical_name,
            raw_text=raw_text,
            source_sentence=source_sentence,
            extraction_type="semantic",
            confidence=0.85,
            category=None,
            optional=False,
            negated=False,
        ))

    return results
