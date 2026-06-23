# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Normalisation des offres.

Ce module normalise toutes les offres pour un traitement uniforme.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from src.offer_normalization import normalize_france_travail_offer

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_OFFERS_PATH = PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json"
NORMALIZED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_normalisees.json"


def normalize_all_offers() -> Dict[str, Any]:
    """Normalise toutes les offres.

    Si le fichier raw n'existe pas ou est corrompu, utilise le fichier
    enrichi existant comme source.

    Returns:
        Statistiques de la normalisation.
    """
    stats = {
        "total_offers": 0,
        "normalized": 0,
        "errors": 0,
    }
    
    ENRICHED_PATH = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"
    
    source_path = RAW_OFFERS_PATH
    source_offers = None
    
    if RAW_OFFERS_PATH.exists():
        try:
            with RAW_OFFERS_PATH.open("r", encoding="utf-8") as f:
                source_offers = json.load(f)
            if not isinstance(source_offers, list):
                source_offers = None
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Fichier raw corrompu (%s), tentative avec fichier enrichi", e)
            source_offers = None
    
    if source_offers is None and ENRICHED_PATH.exists():
        logger.info("Utilisation du fichier enrichi comme source")
        try:
            with ENRICHED_PATH.open("r", encoding="utf-8") as f:
                source_offers = json.load(f)
            source_path = ENRICHED_PATH
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Fichier enrichi aussi invalide: %s", e)
            return stats
    
    if source_offers is None:
        logger.warning("Aucun fichier d'offres disponible")
        return stats
    
    try:
        stats["total_offers"] = len(source_offers)
        
        normalized_offers = []
        for offer in source_offers:
            try:
                normalized = normalize_france_travail_offer(offer)
                normalized_offers.append(normalized)
                stats["normalized"] += 1
            except Exception as e:
                logger.error("Erreur normalisation offre %s: %s", offer.get('id'), e)
                stats["errors"] += 1
        
        NORMALIZED_OFFERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with NORMALIZED_OFFERS_PATH.open("w", encoding="utf-8") as f:
            json.dump(normalized_offers, f, ensure_ascii=False, indent=2)
        
        logger.info("Normalisation terminee: %s/%s offres", stats['normalized'], stats['total_offers'])
        
    except Exception as e:
        logger.error("Erreur normalisation: %s", e)
        stats["errors"] += 1
        raise
    
    return stats
