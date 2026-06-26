# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Extraction des compétences depuis les expériences professionnelles.

Ce module transforme l'intitulé et la description d'une expérience en
compétences exploitables par le profil utilisateur. La logique reste
conservatrice: elle privilégie les compétences observables dans le texte
et réutilise les normalisations canoniques du projet.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.ner.skill_normalizer import canonicalize_skill_name, normalize_skill_lookup
from src.skill_extraction import extract_skills_from_offer
from src.skill_extraction.savoir_faire_extractor import extract_savoir_faire

_DEFAULT_SOURCE = "professional_experience"

_CUSTOM_RULES: Sequence[Tuple[re.Pattern[str], str, float, str]] = (
    (re.compile(r"\bgitlab\s+ci(?:/cd)?\b", re.IGNORECASE), "GitLab CI/CD", 0.96, "gitlab ci"),
    (re.compile(r"\b(?:développement|developpement)\s+d['’]apis?\b", re.IGNORECASE), "Développement d'API", 0.92, "developpement api"),
    (re.compile(r"\btests?\s+automatis[ée]s?\b|\bautomatisation\s+des\s+tests\b", re.IGNORECASE), "Tests automatisés", 0.93, "tests automatises"),
    (re.compile(r"\bmanagement\s+d['’]?[ée]quipe\b|\bgestion\s+d['’]?[ée]quipe\b|\bencadrement\s+d['’]?[ée]quipe\b", re.IGNORECASE), "Management d'équipe", 0.90, "management equipe"),
    (re.compile(r"\bcoordination\s+technique\b", re.IGNORECASE), "Coordination technique", 0.88, "coordination technique"),
    (re.compile(r"\bplanification(?:\s+des\s+interventions)?\b", re.IGNORECASE), "Planification", 0.86, "planification"),
    (re.compile(r"\bmaintenance\s+technique\b|\bmaintenance\s+du\s+parc\b|\bmaintenance\s+du\s+mat[ée]riel\b", re.IGNORECASE), "Maintenance technique", 0.85, "maintenance technique"),
    (re.compile(r"\br[ée]seau\s+audio\b|\breseau\s+audio\b", re.IGNORECASE), "Réseau audio", 0.90, "reseau audio"),
    (re.compile(r"\bmixage(?:\s+(?:audio|sur\s+console\s+num[ée]rique))?\b", re.IGNORECASE), "Mixage audio", 0.88, "mixage audio"),
    (re.compile(r"\bconsole\s+num[ée]rique\b|\bconsole\s+digitale\b", re.IGNORECASE), "Console numérique", 0.88, "console numerique"),
    (re.compile(r"\bdante\b", re.IGNORECASE), "Dante", 0.94, "dante"),
)


def _normalize_existing_skills(existing_skills: Optional[Iterable[str]]) -> set[str]:
    """Retourne l'ensemble des compétences déjà présentes dans le profil.

    Args:
        existing_skills: Compétences déjà validées par l'utilisateur.

    Returns:
        Ensemble de clés normalisées pour la déduplication.
    """

    normalized: set[str] = set()
    for skill in existing_skills or []:
        key = normalize_skill_lookup(skill)
        if key:
            normalized.add(key)
    return normalized


def _clean_text(value: object) -> str:
    """Nettoie un texte pour les comparaisons et l'affichage.

    Args:
        value: Valeur brute.

    Returns:
        Chaîne nettoyée.
    """

    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def _add_candidate(
    result: "OrderedDict[str, Dict[str, object]]",
    *,
    name: str,
    raw_text: str,
    source_text: str,
    confidence: float,
    reason: str,
    existing_keys: set[str],
) -> None:
    """Ajoute une compétence candidate en évitant les doublons.

    Args:
        result: Dictionnaire ordonné des compétences retenues.
        name: Nom canonique proposé.
        raw_text: Extrait brut d'origine.
        source_text: Texte source ayant déclenché l'extraction.
        confidence: Confiance métier entre 0.0 et 1.0.
        reason: Justification courte de l'extraction.
        existing_keys: Compétences déjà présentes dans le profil.
    """

    canonical = canonicalize_skill_name(name)
    key = normalize_skill_lookup(canonical)
    if not canonical or not key or key in existing_keys:
        return

    payload = {
        "name": canonical,
        "normalized_name": key,
        "source": _DEFAULT_SOURCE,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "raw_text": _clean_text(raw_text) or canonical,
        "source_text": _clean_text(source_text) or _clean_text(raw_text) or canonical,
        "reason": reason,
    }

    current = result.get(key)
    if current is None or float(payload["confidence"]) > float(current["confidence"]):
        result[key] = payload


def _combined_text(job_title: str, description: str) -> str:
    """Fusionne les champs texte de l'expérience.

    Args:
        job_title: Intitulé du poste.
        description: Description des missions.

    Returns:
        Texte exploitable par les extracteurs.
    """

    parts = [_clean_text(job_title), _clean_text(description)]
    return "\n".join(part for part in parts if part)


def _extract_rule_based_skills(text: str, existing_keys: set[str]) -> List[Dict[str, object]]:
    """Détecte les compétences via un jeu de règles métier explicites.

    Args:
        text: Texte fusionné de l'expérience.
        existing_keys: Compétences déjà présentes dans le profil.

    Returns:
        Liste de compétences candidates.
    """

    result: "OrderedDict[str, Dict[str, object]]" = OrderedDict()
    for pattern, canonical_name, confidence, reason in _CUSTOM_RULES:
        for match in pattern.finditer(text):
            _add_candidate(
                result,
                name=canonical_name,
                raw_text=match.group(0),
                source_text=text,
                confidence=confidence,
                reason=reason,
                existing_keys=existing_keys,
            )
    return list(result.values())


def extract_skills_from_experience(
    job_title: str,
    description: str,
    existing_skills: Optional[List[str]] = None,
) -> List[Dict[str, object]]:
    """Extrait les compétences d'une expérience professionnelle.

    Le service analyse à la fois l'intitulé et la description afin de
    proposer des compétences réutilisables pour le profil utilisateur.
    Les compétences déjà présentes dans le profil sont filtrées afin
    d'éviter les doublons lors de la confirmation.

    Args:
        job_title: Intitulé du poste de l'expérience.
        description: Description des missions et responsabilités.
        existing_skills: Compétences déjà enregistrées sur le profil.

    Returns:
        Liste de dictionnaires JSON-compatibles contenant au minimum
        ``name``, ``source`` et ``confidence``.

    Raises:
        ValueError: Si aucune information exploitable n'est fournie.
    """

    combined_text = _combined_text(job_title, description)
    if not combined_text:
        raise ValueError("Une expérience doit contenir au moins un intitulé ou une description exploitable.")

    existing_keys = _normalize_existing_skills(existing_skills)
    candidates: "OrderedDict[str, Dict[str, object]]" = OrderedDict()

    # Les compétences explicites du pipeline global restent utiles ici,
    # mais nous les réétiquetons comme provenant de l'expérience.
    for skill in extract_skills_from_offer(combined_text):
        _add_candidate(
            candidates,
            name=skill.canonical_name,
            raw_text=skill.raw_text,
            source_text=skill.source_sentence,
            confidence=float(skill.confidence),
            reason="compétence explicite",
            existing_keys=existing_keys,
        )

    for canonical_name, raw_text, source_sentence in extract_savoir_faire(combined_text):
        _add_candidate(
            candidates,
            name=canonical_name,
            raw_text=raw_text,
            source_text=source_sentence,
            confidence=0.88,
            reason="savoir-faire métier",
            existing_keys=existing_keys,
        )

    for candidate in _extract_rule_based_skills(combined_text, existing_keys):
        key = str(candidate["normalized_name"])
        current = candidates.get(key)
        if current is None or float(candidate["confidence"]) > float(current["confidence"]):
            candidates[key] = candidate

    return sorted(
        candidates.values(),
        key=lambda item: (-float(item["confidence"]), str(item["name"]).lower()),
    )
