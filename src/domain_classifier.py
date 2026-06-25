# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Classification des domaines et métiers pour les offres d'emploi.

Ce module identifie le domaine professionnel, la famille métier,
et le métier principal d'une offre en utilisant les codes ROME,
les intitulés structurés, et le contenu textuel.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from src.domain_config import load_job_domains


def _strip_accents(value: str) -> str:
    """Supprime les accents d'une chaîne."""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_text(value: str) -> str:
    """Normalise un texte pour comparaison."""
    if not value:
        return ""
    text = _strip_accents(value.lower())
    text = re.sub(r"[^\w\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_rome_code(offer: Dict[str, Any]) -> Optional[str]:
    """Extrait le code ROME d'une offre.

    Args:
        offer: Dictionnaire de l'offre.

    Returns:
        Code ROME ou None.
    """
    rome = offer.get("codeROME") or offer.get("romeCode") or offer.get("rome")
    if rome:
        return str(rome).strip()
    return None


def _extract_job_title(offer: Dict[str, Any]) -> str:
    """Extrait le titre du métier d'une offre.

    Args:
        offer: Dictionnaire de l'offre.

    Returns:
        Titre du métier.
    """
    for key in ("intitule", "titre", "intitule_poste", "libelle", "metier"):
        value = offer.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def _extract_description(offer: Dict[str, Any]) -> str:
    """Extrait la description d'une offre.

    Args:
        offer: Dictionnaire de l'offre.

    Returns:
        Description de l'offre.
    """
    description = offer.get("description")
    if description:
        return str(description)
    return ""


def _match_rome_to_domain(rome_code: str) -> Optional[Dict[str, Any]]:
    """Associe un code ROME à un domaine métier.

    Args:
        rome_code: Code ROME à associer.

    Returns:
        Domaine correspondant ou None.
    """
    if not rome_code:
        return None

    domains = load_job_domains()
    for domain in domains:
        rome_codes = domain.get("rome_codes", [])
        if rome_code in rome_codes:
            return domain

    return None


def _match_title_to_domain(title: str) -> Optional[Dict[str, Any]]:
    """Associe un titre de métier à un domaine par mots-clés.

    Args:
        title: Titre du métier.

    Returns:
        Domaine correspondant ou None.
    """
    if not title:
        return None

    title_norm = _normalize_text(title)
    domains = load_job_domains()

    best_match = None
    best_score = 0

    for domain in domains:
        queries = domain.get("queries", [])
        score = 0
        for query in queries:
            query_norm = _normalize_text(query)
            if query_norm in title_norm:
                score += len(query_norm)
        if score > best_score:
            best_score = score
            best_match = domain

    return best_match if best_score > 0 else None


def _match_description_to_domain(description: str) -> Optional[Dict[str, Any]]:
    """Associe une description à un domaine par mots-clés.

    Args:
        description: Description de l'offre.

    Returns:
        Domaine correspondant ou None.
    """
    if not description:
        return None

    desc_norm = _normalize_text(description[:500])
    domains = load_job_domains()

    best_match = None
    best_score = 0

    for domain in domains:
        queries = domain.get("queries", [])
        score = 0
        for query in queries:
            query_norm = _normalize_text(query)
            if query_norm in desc_norm:
                score += len(query_norm)
        if score > best_score:
            best_score = score
            best_match = domain

    return best_match if best_score > 5 else None


def classify_offer_domain(offer: Dict[str, Any]) -> Dict[str, Any]:
    """Classifie le domaine d'une offre.

    Utilise en priorité le code ROME, puis le titre, puis la description.

    Args:
        offer: Dictionnaire de l'offre.

    Returns:
        Dictionnaire contenant:
        - domain_id: Identifiant du domaine
        - domain_name: Nom du domaine
        - job_family: Famille métier
        - job_title: Titre du métier
        - confidence: Score de confiance (0.0 à 1.0)
        - method: Méthode de classification utilisée
    """
    result = {
        "domain_id": "unknown",
        "domain_name": "Non classifié",
        "job_family": "",
        "job_title": "",
        "confidence": 0.0,
        "method": "none",
    }

    job_title = _extract_job_title(offer)
    result["job_title"] = job_title

    rome_code = _extract_rome_code(offer)
    if rome_code:
        domain = _match_rome_to_domain(rome_code)
        if domain:
            result["domain_id"] = domain.get("id", "unknown")
            result["domain_name"] = domain.get("name", "Non classifié")
            result["job_family"] = domain.get("name", "")
            result["confidence"] = 0.95
            result["method"] = "rome_code"
            return result

    if job_title:
        domain = _match_title_to_domain(job_title)
        if domain:
            result["domain_id"] = domain.get("id", "unknown")
            result["domain_name"] = domain.get("name", "Non classifié")
            result["job_family"] = domain.get("name", "")
            result["confidence"] = 0.85
            result["method"] = "job_title"
            return result

    description = _extract_description(offer)
    if description:
        domain = _match_description_to_domain(description)
        if domain:
            result["domain_id"] = domain.get("id", "unknown")
            result["domain_name"] = domain.get("name", "Non classifié")
            result["job_family"] = domain.get("name", "")
            result["confidence"] = 0.60
            result["method"] = "description"
            return result

    return result


def classify_multiple_offers(offers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Classifie le domaine de plusieurs offres.

    Args:
        offers: Liste d'offres.

    Returns:
        Liste des classifications.
    """
    return [classify_offer_domain(offer) for offer in offers]


def get_domain_statistics(offers: List[Dict[str, Any]]) -> Dict[str, int]:
    """Calcule les statistiques de répartition par domaine.

    Args:
        offers: Liste d'offres.

    Returns:
        Dictionnaire {domain_name: count}.
    """
    stats: Dict[str, int] = {}
    for offer in offers:
        classification = classify_offer_domain(offer)
        domain_name = classification["domain_name"]
        stats[domain_name] = stats.get(domain_name, 0) + 1
    return stats
