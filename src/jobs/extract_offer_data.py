# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Extraction des données des offres.

Ce module extrait les compétences, diplômes, salaires et télétravail
de toutes les offres en utilisant le pipeline d'extraction.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from src.predict import extract_job_offer
from src.jobs.cache import cache_store, compute_hash
from src.jobs.status import task_status

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_normalisees.json"
ENRICHED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"


def extract_all_offer_data() -> Dict[str, Any]:
    """Extrait les données de toutes les offres.

    Returns:
        Statistiques de l'extraction.
    """
    stats = {
        "total_offers": 0,
        "processed": 0,
        "skipped": 0,
        "errors": 0,
    }
    
    if not NORMALIZED_OFFERS_PATH.exists():
        logger.warning(f"Fichier introuvable: {NORMALIZED_OFFERS_PATH}")
        return stats
    
    try:
        with NORMALIZED_OFFERS_PATH.open("r", encoding="utf-8") as f:
            normalized_offers = json.load(f)
        
        stats["total_offers"] = len(normalized_offers)
        
        enriched_offers = []
        for i, offer in enumerate(normalized_offers):
            offer_id = offer.get("id", f"unknown_{i}")
            
            try:
                # Vérifier si l'offre a déjà été extraite
                cache_key = f"offer_extraction:{offer_id}"
                offer_hash = compute_hash(offer)
                
                cached = cache_store.get(cache_key)
                if cached and cached.get("input_hash") == offer_hash:
                    # Offre inchangée, utiliser le cache
                    enriched_offers.append(cached["value"])
                    stats["skipped"] += 1
                    continue
                
                # Extraire les données
                description = offer.get("description", "")
                extraction = extract_job_offer(description, debug=False)
                
                # Créer l'offre enrichie
                enriched = offer.copy()
                
                # Mapper les champs extraits
                if extraction.get("competences_requises_noms"):
                    enriched["competences"] = extraction["competences_requises_noms"]
                
                if extraction.get("salaires"):
                    salary_values = []
                    for salaire in extraction["salaires"]:
                        import re
                        numbers = re.findall(r'\d[\d\s]{1,6}', salaire)
                        for num in numbers:
                            cleaned = num.replace(" ", "")
                            try:
                                value = int(cleaned)
                                if value >= 1000:
                                    salary_values.append(value)
                            except ValueError:
                                pass
                    
                    if salary_values:
                        enriched["salaire_min"] = min(salary_values)
                        enriched["salaire_max"] = max(salary_values)
                
                if extraction.get("distanciel"):
                    enriched["teletravail"] = extraction["distanciel"]
                
                if extraction.get("diplomes_requis"):
                    enriched["diplomes_requis"] = extraction["diplomes_requis"]
                
                enriched["_extraction_metadata"] = {
                    "extracted": True,
                    "competences_count": len(extraction.get("competences_requises_noms", [])),
                    "diplomes_count": len(extraction.get("diplomes_requis", [])),
                    "has_salary": bool(extraction.get("salaires")),
                    "has_teletravail": extraction.get("distanciel") is not None,
                }
                
                enriched_offers.append(enriched)
                stats["processed"] += 1
                
                # Mettre en cache
                cache_store.set(
                    cache_key,
                    enriched,
                    input_hash=offer_hash,
                    source_version="1.0",
                    model_version="1.0",
                )
                
                # Log progress
                if (i + 1) % 100 == 0:
                    logger.info(f"Extraction: {i + 1}/{stats['total_offers']}")
                
            except Exception as e:
                logger.error(f"Erreur extraction offre {offer_id}: {e}")
                task_status.add_error("extract_offer_data", offer_id, "extraction", str(e))
                stats["errors"] += 1
                # Continuer avec l'offre non enrichie
                enriched_offers.append(offer)
        
        # Sauvegarder
        ENRICHED_OFFERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ENRICHED_OFFERS_PATH.open("w", encoding="utf-8") as f:
            json.dump(enriched_offers, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Extraction terminée: {stats['processed']} traitées, {stats['skipped']} ignorées")
        
    except Exception as e:
        logger.error(f"Erreur extraction: {e}")
        stats["errors"] += 1
        raise
    
    return stats
