# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Script de diagnostic pour l'affichage des offres.

Ce module permet d'inspecter le chemin complet des données d'une offre :
données brutes, normalisées, matching, cache, et ViewModel final.

Usage::

    python -m src.debug_offer_display --offer-id IDENTIFIANT
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from src.cache_reader import (
    get_precomputed_matches,
    get_precomputed_offers,
    get_cache_schema_version,
    is_cache_schema_valid,
)
from src.presentation.offer_view_model import (
    build_match_view_model,
    build_offer_view_model,
    normalize_criterion_scores,
    resolve_offer_title,
    resolve_offer_location,
    resolve_offer_url,
)
from src.services.offer_normalization import normalize_offer_for_matching

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_OFFERS_PATH = PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json"
ENRICHED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"
NORMALIZED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_normalisees.json"
MATCHES_PATH = PROJECT_ROOT / "data" / "processed" / "matches.json"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_raw_offer(offer_id: str) -> Optional[Dict[str, Any]]:
    for path in (RAW_OFFERS_PATH, ENRICHED_OFFERS_PATH, NORMALIZED_OFFERS_PATH):
        data = _load_json(path)
        if isinstance(data, list):
            for offer in data:
                if isinstance(offer, dict):
                    oid = str(offer.get("id") or offer.get("id_offre") or "")
                    if oid == offer_id:
                        return offer
    return None


def _find_enriched_offer(offer_id: str) -> Optional[Dict[str, Any]]:
    data = _load_json(ENRICHED_OFFERS_PATH)
    if isinstance(data, list):
        for offer in data:
            if isinstance(offer, dict):
                oid = str(offer.get("id") or offer.get("id_offre") or "")
                if oid == offer_id:
                    return offer
    return None


def _find_match(offer_id: str, user_id: int = 1) -> Optional[Dict[str, Any]]:
    data = _load_json(MATCHES_PATH)
    if isinstance(data, dict):
        user_matches = data.get(str(user_id)) or data.get(user_id) or []
        if isinstance(user_matches, list):
            for match in user_matches:
                mid = str(match.get("offer_id") or match.get("offer_identifier") or "")
                if mid == offer_id:
                    return match
    return None


def _safe_dump(data: Any, max_depth: int = 4) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def diagnose_offer(offer_id: str, user_id: int = 1) -> Dict[str, Any]:
    """Diagnostique le chemin complet des données d'une offre.

    Args:
        offer_id: Identifiant de l'offre.
        user_id: Identifiant utilisateur pour les matchings.

    Returns:
        Dictionnaire de diagnostic complet.
    """
    result: Dict[str, Any] = {"offer_id": offer_id}

    schema_version = get_cache_schema_version()
    schema_valid = is_cache_schema_valid()
    result["cache_schema"] = {
        "version": schema_version,
        "expected": 2,
        "valid": schema_valid,
    }

    raw_offer = _find_raw_offer(offer_id)
    result["raw_offer_found"] = raw_offer is not None
    if raw_offer:
        result["raw_offer_keys"] = list(raw_offer.keys())
        result["raw_offer_title_fields"] = {
            "title": raw_offer.get("title"),
            "intitule": raw_offer.get("intitule"),
            "intitule_poste": raw_offer.get("intitule_poste"),
            "metier": raw_offer.get("metier"),
            "libelle": raw_offer.get("libelle"),
            "romeLibelle": raw_offer.get("romeLibelle"),
        }

    enriched_offer = _find_enriched_offer(offer_id)
    result["enriched_offer_found"] = enriched_offer is not None
    if enriched_offer:
        result["enriched_offer_keys"] = list(enriched_offer.keys())
        normalized = normalize_offer_for_matching(enriched_offer, source=enriched_offer.get("source") or "France Travail")
        result["normalized_offer"] = normalized
        result["resolved_title"] = resolve_offer_title(enriched_offer)
        result["resolved_title_from_normalized"] = resolve_offer_title(normalized)
        result["resolved_location"] = resolve_offer_location(enriched_offer)
        result["resolved_url"] = resolve_offer_url(enriched_offer, offer_id)

    match = _find_match(offer_id, user_id)
    result["match_found"] = match is not None
    if match:
        details = match.get("details") or {}
        result["match_score"] = match.get("score")
        result["match_details_keys"] = list(details.keys())
        result["criterion_scores"] = details.get("criterion_scores")
        result["sous_scores"] = details.get("sous_scores")
        result["explanation_subscores"] = (details.get("explanation") or {}).get("subscores")

        normalized_scores = normalize_criterion_scores(details)
        result["normalized_criterion_scores"] = {
            key: {"score": v.get("score"), "evaluated": v.get("evaluated"), "label": v.get("label")}
            for key, v in normalized_scores.items()
        }

    if enriched_offer and match:
        vm = build_match_view_model(match, enriched_offer, offer_identifier=offer_id)
        from dataclasses import asdict
        result["view_model"] = asdict(vm)
    elif enriched_offer:
        vm = build_offer_view_model(enriched_offer, offer_identifier=offer_id)
        from dataclasses import asdict
        result["view_model"] = asdict(vm)

    return result


def main() -> None:
    """Point d'entrée du script de diagnostic."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Diagnostic d'affichage d'offre")
    parser.add_argument("--offer-id", required=True, help="Identifiant de l'offre")
    parser.add_argument("--user-id", type=int, default=1, help="Identifiant utilisateur (défaut: 1)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute")
    args = parser.parse_args()

    result = diagnose_offer(args.offer_id, user_id=args.user_id)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"=== Diagnostic offre {args.offer_id} ===\n")

        schema = result.get("cache_schema", {})
        print(f"Cache schema: v{schema.get('version')} (attendu: v{schema.get('expected')}) — {'OK' if schema.get('valid') else 'OBSOLETE'}")
        print()

        if result.get("raw_offer_found"):
            print("Titres bruts:")
            for key, value in result.get("raw_offer_title_fields", {}).items():
                print(f"  {key}: {value!r}")
        else:
            print("Offre brute: NON TROUVÉE")
        print()

        if result.get("enriched_offer_found"):
            print(f"Titre résolu: {result.get('resolved_title')}")
            print(f"Localisation: {result.get('resolved_location')}")
            print(f"URL: {result.get('resolved_url')}")
        else:
            print("Offre enrichie: NON TROUVÉE")
        print()

        if result.get("match_found"):
            print(f"Score match: {result.get('match_score')}")
            print("Sous-scores normalisés:")
            for key, info in result.get("normalized_criterion_scores", {}).items():
                status = "évalué" if info.get("evaluated") else "non évalué"
                score = info.get("score")
                score_text = f"{score:.1f}" if score is not None else "—"
                print(f"  {info.get('label', key)}: {score_text} ({status})")
        else:
            print("Matching: NON TROUVÉ")
        print()

        vm = result.get("view_model")
        if vm:
            print("ViewModel final:")
            print(f"  title: {vm.get('title')}")
            print(f"  company: {vm.get('company')}")
            print(f"  location: {vm.get('location')}")
            print(f"  global_score: {vm.get('global_score')}")
            print(f"  url: {vm.get('url')}")
            print(f"  matched_skills: {vm.get('matched_skills', [])[:5]}")
            print(f"  missing_skills: {vm.get('missing_skills', [])[:5]}")


if __name__ == "__main__":
    main()
