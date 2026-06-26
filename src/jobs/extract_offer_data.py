# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Extraction des données structurées des offres normalisées.

Ce module transforme les offres normalisées en offres enrichies en
ajoutant les données extraites depuis le texte source. Il agit comme
source de vérité pour l'étape 3 du rafraîchissement complet et sert
également de base à l'invalidation des caches des étapes suivantes.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from src.jobs.cache import cache_store, compute_hash
from src.jobs.status import task_status
from src.predict import extract_job_offer

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_normalisees.json"
ENRICHED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"
EXTRACTION_CACHE_VERSION = "2.0"


def _utcnow_iso() -> str:
    """Retourne l'horodatage UTC courant au format ISO.

    Returns:
        Chaîne ISO 8601 sans microsecondes.
    """
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _first_text(values: Iterable[object]) -> str:
    """Retourne la première valeur textuelle non vide d'une séquence.

    Args:
        values: Valeurs candidates à concaténer.

    Returns:
        Première chaîne non vide, ou chaîne vide si rien n'est exploitable.
    """
    for value in values:
        if value in (None, ""):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _offer_identifier(offer: Dict[str, Any], fallback_index: int) -> str:
    """Résout l'identifiant stable d'une offre.

    Args:
        offer: Offre normalisée.
        fallback_index: Index utilisé si aucun identifiant n'est disponible.

    Returns:
        Identifiant textuel de l'offre.
    """
    identifier = _first_text(
        (
            offer.get("id"),
            offer.get("id_offre"),
            offer.get("idOffre"),
            offer.get("idOfr"),
            offer.get("numero_offre"),
        )
    )
    if identifier:
        return identifier
    return f"unknown_{fallback_index}"


def _offer_source_text(offer: Dict[str, Any]) -> str:
    """Construit le texte source utilisé par l'extracteur.

    Args:
        offer: Offre normalisée.

    Returns:
        Texte d'entrée du moteur d'extraction. Chaîne vide si aucun texte
        pertinent n'est disponible.
    """
    return "\n".join(
        part
        for part in (
            _first_text((offer.get("description"), offer.get("texte_source"), offer.get("content"))),
            _first_text((offer.get("intitule"), offer.get("titre"), offer.get("metier"))),
        )
        if part
    ).strip()


def _has_meaningful_extraction(extraction: Dict[str, Any]) -> bool:
    """Indique si une extraction contient des données réellement utiles.

    Args:
        extraction: Résultat brut renvoyé par l'extracteur.

    Returns:
        True si au moins un élément structuré a été identifié.
    """
    return any(
        [
            bool(extraction.get("competences_requises_noms")),
            bool(extraction.get("competences_requises_detaillees")),
            bool(extraction.get("diplomes_requis")),
            bool(extraction.get("salaires")),
            bool(extraction.get("contacts")),
            extraction.get("distanciel") not in (None, ""),
        ]
    )


def _build_extraction_metadata(
    *,
    offer: Dict[str, Any],
    source_hash: str,
    extraction: Dict[str, Any],
) -> Dict[str, Any]:
    """Construit les métadonnées de traçabilité de l'extraction.

    Args:
        offer: Offre normalisée d'origine.
        source_hash: Hash de l'offre normalisée utilisée comme entrée.
        extraction: Résultat brut de l'extracteur.

    Returns:
        Dictionnaire de métadonnées persisté avec l'offre enrichie.
    """
    competences = extraction.get("competences_requises_noms") or []
    diplomes = extraction.get("diplomes_requis") or []
    salaires = extraction.get("salaires") or []
    contacts = extraction.get("contacts") or []
    has_teletravail = extraction.get("distanciel") not in (None, "")
    has_meaningful_data = _has_meaningful_extraction(extraction)
    offer_id = _first_text((offer.get("id"), offer.get("id_offre"), offer.get("numero_offre")))

    return {
        "extracted": has_meaningful_data,
        "complete": has_meaningful_data,
        "source_offer_id": offer_id,
        "source_offer_hash": source_hash,
        "extraction_version": EXTRACTION_CACHE_VERSION,
        "extracted_at": _utcnow_iso(),
        "competences_count": len(competences),
        "competences_detaillees_count": len(extraction.get("competences_requises_detaillees") or []),
        "diplomes_count": len(diplomes),
        "salaires_count": len(salaires),
        "contacts_count": len(contacts),
        "has_salary": bool(salaires),
        "has_teletravail": has_teletravail,
    }


def _merge_extraction(offer: Dict[str, Any], extraction: Dict[str, Any], source_hash: str) -> Dict[str, Any]:
    """Fusionne l'offre normalisée avec les données extraites.

    Args:
        offer: Offre normalisée d'entrée.
        extraction: Résultat brut de l'extracteur.
        source_hash: Hash de l'offre normalisée utilisée comme entrée.

    Returns:
        Offre enrichie prête à être persistée.
    """
    enriched = offer.copy()

    competences = extraction.get("competences_requises_noms") or []
    if competences:
        enriched["competences"] = list(dict.fromkeys(str(item).strip() for item in competences if str(item).strip()))

    salaries = extraction.get("salaires") or []
    if salaries:
        salary_values = []
        for salaire in salaries:
            numbers = re.findall(r"\d[\d\s]{1,6}", str(salaire))
            for num in numbers:
                cleaned = num.replace(" ", "")
                try:
                    value = int(cleaned)
                except ValueError:
                    continue
                if value >= 1000:
                    salary_values.append(value)
        if salary_values:
            enriched["salaire_min"] = min(salary_values)
            enriched["salaire_max"] = max(salary_values)

    teletravail = extraction.get("distanciel")
    if teletravail:
        enriched["teletravail"] = teletravail

    diplomes = extraction.get("diplomes_requis") or []
    if diplomes:
        enriched["diplomes_requis"] = diplomes

    enriched["contacts"] = extraction.get("contacts") or []
    enriched["competences_requises_detaillees"] = extraction.get("competences_requises_detaillees") or []
    enriched["competences_requises_noms"] = list(dict.fromkeys(extraction.get("competences_requises_noms") or []))
    enriched["_extraction_metadata"] = _build_extraction_metadata(
        offer=offer,
        source_hash=source_hash,
        extraction=extraction,
    )
    return enriched


def extraction_is_complete(offer: Dict[str, Any], current_version: str) -> bool:
    """Vérifie si une offre enrichie possède une extraction exploitable.

    Le test de complétude ne se base pas uniquement sur un horodatage.
    Il exige une extraction réellement renseignée, cohérente avec l'offre
    source et produite par la version actuelle de l'extracteur.

    Args:
        offer: Offre enrichie issue du cache ou du calcul.
        current_version: Version attendue de l'extracteur.

    Returns:
        True si l'extraction peut être réutilisée sans recalcul.
    """
    if not isinstance(offer, dict):
        return False

    metadata = offer.get("_extraction_metadata")
    if not isinstance(metadata, dict):
        return False

    offer_id = _first_text((offer.get("id"), offer.get("id_offre"), offer.get("numero_offre")))
    if not offer_id:
        return False

    if _first_text((metadata.get("source_offer_id"),)) != offer_id:
        return False

    if _first_text((metadata.get("extraction_version"), metadata.get("model_version"))) != current_version:
        return False

    if not metadata.get("extracted_at"):
        return False

    if metadata.get("complete") is False or metadata.get("extracted") is False:
        return False

    return bool(
        metadata.get("competences_count", 0)
        or metadata.get("competences_detaillees_count", 0)
        or metadata.get("diplomes_count", 0)
        or metadata.get("salaires_count", 0)
        or metadata.get("contacts_count", 0)
        or metadata.get("has_teletravail")
    )


def _classify_skip_reason(
    *,
    cache_entry: Optional[Dict[str, Any]],
    source_text: str,
    current_version: str,
    offer: Dict[str, Any],
) -> str:
    """Attribue une raison d'exclusion lisible pour le diagnostic.

    Args:
        cache_entry: Entrée du cache si elle existe.
        source_text: Texte source exploitable pour l'extraction.
        current_version: Version attendue de l'extracteur.
        offer: Offre normalisée.

    Returns:
        Libellé court de diagnostic.
    """
    if not source_text:
        return "texte absent"
    if cache_entry is None:
        return "cache absent"
    cached_offer = cache_entry.get("value") if isinstance(cache_entry, dict) else None
    if not isinstance(cached_offer, dict):
        return "cache invalide"
    if _first_text((cache_entry.get("source_version"), cache_entry.get("model_version"))) not in {"", current_version}:
        return "extraction obsolète"
    if not extraction_is_complete(cached_offer, current_version):
        return "extraction incomplète"
    cached_id = _first_text((cached_offer.get("id"), cached_offer.get("id_offre"), cached_offer.get("numero_offre")))
    offer_id = _offer_identifier(offer, 0)
    if cached_id and cached_id != offer_id:
        return "offre incohérente"
    return "déjà extraite et valide"


def extract_all_offer_data() -> Dict[str, Any]:
    """Extrait et persiste les données structurées de toutes les offres.

    Returns:
        Dictionnaire de statistiques détaillant les offres traitées,
        ignorées et les principales raisons de classification.
    """
    stats: Dict[str, Any] = {
        "total_offers": 0,
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "reasons": {},
    }

    if not NORMALIZED_OFFERS_PATH.exists():
        logger.warning("Fichier introuvable: %s", NORMALIZED_OFFERS_PATH)
        return stats

    try:
        with NORMALIZED_OFFERS_PATH.open("r", encoding="utf-8") as fh:
            normalized_offers = json.load(fh)

        if not isinstance(normalized_offers, list):
            raise ValueError("Le fichier d'offres normalisées doit contenir une liste JSON.")

        stats["total_offers"] = len(normalized_offers)
        enriched_offers = []
        reason_counts: Counter[str] = Counter()

        for index, offer in enumerate(normalized_offers):
            if not isinstance(offer, dict):
                stats["errors"] += 1
                reason_counts["offre invalide"] += 1
                continue

            offer_id = _offer_identifier(offer, index)
            source_text = _offer_source_text(offer)
            offer_hash = compute_hash(offer)
            cache_key = f"offer_extraction:v{EXTRACTION_CACHE_VERSION}:{offer_id}"
            cache_entry = cache_store.get(cache_key)
            cached_offer = cache_entry.get("value") if isinstance(cache_entry, dict) else None

            if (
                isinstance(cache_entry, dict)
                and cache_entry.get("input_hash") == offer_hash
                and isinstance(cached_offer, dict)
                and extraction_is_complete(cached_offer, EXTRACTION_CACHE_VERSION)
            ):
                enriched_offers.append(cached_offer)
                stats["skipped"] += 1
                reason_counts["déjà extraite et valide"] += 1
                continue

            if not source_text:
                enriched_offers.append(offer)
                stats["skipped"] += 1
                reason_counts["texte absent"] += 1
                continue

            try:
                extraction = extract_job_offer(source_text, debug=False)
                enriched = _merge_extraction(offer, extraction, offer_hash)
                enriched_offers.append(enriched)
                stats["processed"] += 1
                if extraction_is_complete(enriched, EXTRACTION_CACHE_VERSION):
                    reason_counts["traitée"] += 1
                else:
                    reason_counts["extraction incomplète"] += 1

                cache_store.set(
                    cache_key,
                    enriched,
                    input_hash=offer_hash,
                    source_version=EXTRACTION_CACHE_VERSION,
                    model_version=EXTRACTION_CACHE_VERSION,
                )
            except Exception as exc:
                logger.error("Erreur extraction offre %s: %s", offer_id, exc)
                task_status.add_error("extract_offer_data", offer_id, "extraction", str(exc))
                stats["errors"] += 1
                reason_counts["erreur"] += 1
                enriched_offers.append(offer)

            if (index + 1) % 500 == 0:
                logger.info(
                    "Extraction en cours: %d/%d offres analysées",
                    index + 1,
                    stats["total_offers"],
                )

        ENRICHED_OFFERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ENRICHED_OFFERS_PATH.open("w", encoding="utf-8") as fh:
            json.dump(enriched_offers, fh, ensure_ascii=False, indent=2)

        stats["reasons"] = dict(reason_counts)
        summary = [
            f"{reason_counts.get('déjà extraite et valide', 0)} déjà extraites et valides",
            f"{reason_counts.get('extraction obsolète', 0)} extraction obsolète",
            f"{reason_counts.get('texte absent', 0)} texte absent",
            f"{reason_counts.get('erreur', 0)} erreurs",
            f"{reason_counts.get('extraction incomplète', 0)} incomplètes",
        ]
        logger.info(
            "Extraction terminée: %s traitées, %s ignorées | %s",
            stats["processed"],
            stats["skipped"],
            ", ".join(summary),
        )

    except Exception as exc:
        logger.error("Erreur extraction: %s", exc)
        stats["errors"] += 1
        raise

    return stats
