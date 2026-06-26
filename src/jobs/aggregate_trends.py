# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Agrégation des tendances du marché.

Ce module agrège les tendances du marché du travail à partir des offres.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from src.trend_aggregation import aggregate_trends
from src.jobs.cache import cache_store, compute_hash

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENRICHED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"
TRENDS_PATH = PROJECT_ROOT / "data" / "processed" / "trends.json"
CACHE_VERSION = "2.0"


def aggregate_all_trends() -> Dict[str, Any]:
    """Agrège les tendances pour tous les territoires.

    Returns:
        Statistiques de l'agrégation.
    """
    stats = {
        "total_offers": 0,
        "territories_processed": 0,
        "errors": 0,
    }
    
    if not ENRICHED_OFFERS_PATH.exists():
        logger.warning(f"Fichier introuvable: {ENRICHED_OFFERS_PATH}")
        return stats
    
    try:
        with ENRICHED_OFFERS_PATH.open("r", encoding="utf-8") as f:
            offers = json.load(f)
        
        stats["total_offers"] = len(offers)
        
        # Extraire les territoires uniques
        territories = set()
        for offer in offers:
            territoire = offer.get("territoire")
            if territoire:
                territories.add(territoire)
        
        # Agréger pour chaque territoire
        all_trends = {}
        
        # Trends globales
        cache_key = f"trends:v{CACHE_VERSION}:global"
        offers_hash = compute_hash(offers)
        
        cached = cache_store.get(cache_key)
        if cached and cached.get("input_hash") == offers_hash:
            all_trends["global"] = cached["value"]
            logger.info("Trends globales depuis cache")
        else:
            trends = aggregate_trends(offers, territoire=None, periode_jours=365)
            all_trends["global"] = trends
            cache_store.set(cache_key, trends, input_hash=offers_hash, source_version=CACHE_VERSION)
            stats["territories_processed"] += 1
        
        # Trends par territoire
        for territory in territories:
            cache_key = f"trends:v{CACHE_VERSION}:{territory}"
            
            cached = cache_store.get(cache_key)
            if cached and cached.get("input_hash") == offers_hash:
                all_trends[territory] = cached["value"]
                continue
            
            trends = aggregate_trends(offers, territoire=territory, periode_jours=365)
            all_trends[territory] = trends
            cache_store.set(cache_key, trends, input_hash=offers_hash, source_version=CACHE_VERSION)
            stats["territories_processed"] += 1
        
        # Sauvegarder
        TRENDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRENDS_PATH.open("w", encoding="utf-8") as f:
            json.dump(all_trends, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Agrégation terminée: {stats['territories_processed']} territoires")
        
    except Exception as e:
        logger.error(f"Erreur agrégation: {e}")
        stats["errors"] += 1
        raise
    
    return stats
