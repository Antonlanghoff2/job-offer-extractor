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

    Returns:
        Statistiques de la normalisation.
    """
    stats = {
        "total_offers": 0,
        "normalized": 0,
        "errors": 0,
    }
    
    if not RAW_OFFERS_PATH.exists():
        logger.warning(f"Fichier introuvable: {RAW_OFFERS_PATH}")
        return stats
    
    try:
        with RAW_OFFERS_PATH.open("r", encoding="utf-8") as f:
            raw_offers = json.load(f)
        
        stats["total_offers"] = len(raw_offers)
        
        normalized_offers = []
        for offer in raw_offers:
            try:
                normalized = normalize_france_travail_offer(offer)
                normalized_offers.append(normalized)
                stats["normalized"] += 1
            except Exception as e:
                logger.error(f"Erreur normalisation offre {offer.get('id')}: {e}")
                stats["errors"] += 1
        
        NORMALIZED_OFFERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with NORMALIZED_OFFERS_PATH.open("w", encoding="utf-8") as f:
            json.dump(normalized_offers, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Normalisation terminée: {stats['normalized']}/{stats['total_offers']} offres")
        
    except Exception as e:
        logger.error(f"Erreur normalisation: {e}")
        stats["errors"] += 1
        raise
    
    return stats
