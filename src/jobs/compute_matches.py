# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Calcul des matchings utilisateur-offre.

Ce module précalcule les matchings pour tous les profils utilisateurs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from src.jobs.cache import cache_store, compute_hash
from src.jobs.status import task_status
from src.services.matching_service import compute_match

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENRICHED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"
USERS_DB_PATH = PROJECT_ROOT / "instance" / "users.json"
MATCHES_PATH = PROJECT_ROOT / "data" / "processed" / "matches.json"


def _load_users() -> List[Dict[str, Any]]:
    """Charge les utilisateurs depuis la base.

    Returns:
        Liste des utilisateurs.
    """
    if not USERS_DB_PATH.exists():
        return []
    
    try:
        with USERS_DB_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("users", [])
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Erreur chargement utilisateurs: {e}")
        return []


def _get_user_profile(user: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait le profil d'un utilisateur.

    Args:
        user: Données utilisateur.

    Returns:
        Profil utilisateur pour le matching.
    """
    return {
        "skills": user.get("skills", []),
        "desired_jobs": user.get("desired_jobs", []),
        "city": user.get("city", ""),
        "postal_code": user.get("postal_code", ""),
        "contract_preference": user.get("contract_preference", ""),
        "remote_preference": user.get("remote_preference", ""),
        "minimum_salary": user.get("minimum_salary"),
        "experiences": user.get("experiences", []),
        "diplomas": user.get("diplomas", []),
    }


def compute_all_matches() -> Dict[str, Any]:
    """Calcule les matchings pour tous les utilisateurs.

    Returns:
        Statistiques du calcul.
    """
    stats = {
        "total_users": 0,
        "users_processed": 0,
        "matches_computed": 0,
        "errors": 0,
    }
    
    if not ENRICHED_OFFERS_PATH.exists():
        logger.warning(f"Fichier introuvable: {ENRICHED_OFFERS_PATH}")
        return stats
    
    try:
        with ENRICHED_OFFERS_PATH.open("r", encoding="utf-8") as f:
            offers = json.load(f)
        
        offers_hash = compute_hash(offers)
        
        users = _load_users()
        stats["total_users"] = len(users)
        
        all_matches = {}
        
        for user in users:
            user_id = user.get("id")
            if not user_id:
                continue
            
            try:
                # Vérifier si le profil a changé
                profile = _get_user_profile(user)
                profile_hash = compute_hash(profile)
                
                cache_key = f"matches:user:{user_id}"
                cached = cache_store.get(cache_key)
                
                if cached and cached.get("input_hash") == compute_hash({"offers": offers_hash, "profile": profile_hash}):
                    all_matches[user_id] = cached["value"]
                    continue
                
                # Calculer les matchings
                user_matches = []
                for offer in offers:
                    try:
                        match = compute_match(profile, offer)
                        user_matches.append({
                            "offer_id": offer.get("id"),
                            "score": match.get("global_score", 0),
                            "matching_skills": match.get("matching_skills", []),
                            "missing_skills": match.get("missing_skills", []),
                            "details": match,
                        })
                        stats["matches_computed"] += 1
                    except Exception as e:
                        logger.error(f"Erreur matching offre {offer.get('id')} pour user {user_id}: {e}")
                        stats["errors"] += 1
                
                # Trier par score
                user_matches.sort(key=lambda x: x["score"], reverse=True)
                
                all_matches[user_id] = user_matches
                stats["users_processed"] += 1
                
                # Mettre en cache
                combined_hash = compute_hash({"offers": offers_hash, "profile": profile_hash})
                cache_store.set(cache_key, user_matches, input_hash=combined_hash)
                
            except Exception as e:
                logger.error(f"Erreur calcul matchings user {user_id}: {e}")
                task_status.add_error("compute_matches", str(user_id), "matching", str(e))
                stats["errors"] += 1
        
        # Sauvegarder
        MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MATCHES_PATH.open("w", encoding="utf-8") as f:
            json.dump(all_matches, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Matchings calculés: {stats['users_processed']} utilisateurs, {stats['matches_computed']} matchings")
        
    except Exception as e:
        logger.error(f"Erreur calcul matchings: {e}")
        stats["errors"] += 1
        raise
    
    return stats
