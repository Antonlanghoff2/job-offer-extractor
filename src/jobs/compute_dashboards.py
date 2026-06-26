# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Calcul des tableaux de bord.

Ce module précalcule les données pour les tableaux de bord.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from src.jobs.cache import cache_store, compute_hash

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENRICHED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"
TRENDS_PATH = PROJECT_ROOT / "data" / "processed" / "trends.json"
DASHBOARDS_PATH = PROJECT_ROOT / "data" / "processed" / "dashboards.json"
CACHE_VERSION = "2.0"


def compute_all_dashboards() -> Dict[str, Any]:
    """Calcule les données des tableaux de bord.

    Returns:
        Statistiques du calcul.
    """
    stats = {
        "dashboards_computed": 0,
        "errors": 0,
    }
    
    if not ENRICHED_OFFERS_PATH.exists():
        logger.warning(f"Fichier introuvable: {ENRICHED_OFFERS_PATH}")
        return stats
    
    if not TRENDS_PATH.exists():
        logger.warning(f"Fichier introuvable: {TRENDS_PATH}")
        return stats
    
    try:
        with ENRICHED_OFFERS_PATH.open("r", encoding="utf-8") as f:
            offers = json.load(f)
        
        with TRENDS_PATH.open("r", encoding="utf-8") as f:
            trends = json.load(f)
        
        offers_hash = compute_hash(offers)
        trends_hash = compute_hash(trends)
        combined_hash = compute_hash({"offers": offers_hash, "trends": trends_hash, "version": CACHE_VERSION})
        
        # Vérifier le cache
        cache_key = f"dashboards:v{CACHE_VERSION}:all"
        cached = cache_store.get(cache_key)
        
        if cached and cached.get("input_hash") == combined_hash:
            logger.info("Dashboards depuis cache")
            stats["dashboards_computed"] = 0
            return stats
        
        # Calculer les dashboards
        dashboards = {}
        
        # Dashboard global
        global_trends = trends.get("global", {})
        dashboards["global"] = {
            "total_offers": len(offers),
            "top_competences": list(global_trends.get("competences", {}).items())[:20],
            "top_metiers": list(global_trends.get("metiers", {}).items())[:20],
            "top_contrats": list(global_trends.get("contrats", {}).items())[:10],
            "territoires": list(set(o.get("territoire") for o in offers if o.get("territoire"))),
        }
        
        # Dashboards par territoire
        for territory, territory_trends in trends.items():
            if territory == "global":
                continue
            
            territory_offers = [o for o in offers if o.get("territoire") == territory]
            
            dashboards[territory] = {
                "total_offers": len(territory_offers),
                "top_competences": list(territory_trends.get("competences", {}).items())[:20],
                "top_metiers": list(territory_trends.get("metiers", {}).items())[:20],
                "top_contrats": list(territory_trends.get("contrats", {}).items())[:10],
            }
        
        stats["dashboards_computed"] = len(dashboards)
        
        # Sauvegarder
        DASHBOARDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DASHBOARDS_PATH.open("w", encoding="utf-8") as f:
            json.dump(dashboards, f, ensure_ascii=False, indent=2)
        
        # Mettre en cache
        cache_store.set(cache_key, dashboards, input_hash=combined_hash, source_version=CACHE_VERSION)
        
        logger.info(f"Dashboards calculés: {stats['dashboards_computed']}")
        
    except Exception as e:
        logger.error(f"Erreur calcul dashboards: {e}")
        stats["errors"] += 1
        raise
    
    return stats
