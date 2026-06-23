# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Import des offres depuis France Travail.

Ce module gère l'import incrémental des offres depuis l'API France Travail.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_OFFERS_PATH = PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json"


def import_latest_offers() -> Dict[str, Any]:
    """Importe les dernières offres depuis France Travail.

    Returns:
        Statistiques de l'import.
    """
    from src.france_travail_client import search_all_offres
    from src.import_offres import REQUETES, TERRITOIRES
    
    stats = {
        "total_offers": 0,
        "new_offers": 0,
        "updated_offers": 0,
        "errors": 0,
    }
    
    try:
        # Charger les offres existantes
        existing_offers = {}
        if RAW_OFFERS_PATH.exists():
            with RAW_OFFERS_PATH.open("r", encoding="utf-8") as f:
                existing_list = json.load(f)
                existing_offers = {o.get("id"): o for o in existing_list if o.get("id")}
        
        # Importer les nouvelles offres
        result = search_all_offres(
            REQUETES,
            page_size=150,
            max_pages=10,
            territoires=TERRITOIRES,
        )
        
        new_offers = result["offers"]
        stats["total_offers"] = len(new_offers)
        
        # Fusionner avec les offres existantes
        for offer in new_offers:
            offer_id = offer.get("id")
            if not offer_id:
                continue
            
            if offer_id in existing_offers:
                stats["updated_offers"] += 1
            else:
                stats["new_offers"] += 1
            
            existing_offers[offer_id] = offer
        
        # Sauvegarder
        RAW_OFFERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RAW_OFFERS_PATH.open("w", encoding="utf-8") as f:
            json.dump(list(existing_offers.values()), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Import terminé: {stats['new_offers']} nouvelles, {stats['updated_offers']} mises à jour")
        
    except Exception as e:
        logger.error(f"Erreur import: {e}")
        stats["errors"] += 1
        raise
    
    return stats
