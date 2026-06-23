# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Lecteur de cache pour les routes Flask.

Ce module fournit des fonctions de lecture des données précalculées
par les tâches de src/jobs/. Les routes Flask doivent utiliser ces
fonctions au lieu de recalculer les données à chaque requête.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.jobs.cache import CacheStore, cache_store
from src.jobs.status import TaskStatus, task_status

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"

ENRICHED_OFFERS_PATH = DATA_PROCESSED / "offres_enrichies.json"
NORMALIZED_OFFERS_PATH = DATA_PROCESSED / "offres_normalisees.json"
TRENDS_PATH = DATA_PROCESSED / "trends.json"
DASHBOARDS_PATH = DATA_PROCESSED / "dashboards.json"
MATCHES_PATH = DATA_PROCESSED / "matches.json"


def _load_json_file(path: Path) -> Optional[Any]:
    """Charge un fichier JSON de manière sécurisée.

    Args:
        path: Chemin du fichier.

    Returns:
        Données JSON ou None si erreur.
    """
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Erreur lecture %s: %s", path, e)
        return None


def get_precomputed_offers() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Retourne les offres précalculées enrichies.

    Returns:
        Tuple (offres, message_erreur).
    """
    data = _load_json_file(ENRICHED_OFFERS_PATH)
    if data is None:
        data = _load_json_file(NORMALIZED_OFFERS_PATH)
    if data is None:
        return [], "Aucune offre précalculée. Lancez python -m src.jobs.refresh_all"
    if not isinstance(data, list):
        return [], "Format d'offres invalide."
    return data, None


def get_precomputed_trends(
    territoire: Optional[str] = None,
    periode_jours: int = 365,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Retourne les tendances précalculées.

    Args:
        territoire: Territoire cible ou None pour global.
        periode_jours: Période en jours (non utilisé si cache).

    Returns:
        Tuple (tendances, message_erreur).
    """
    data = _load_json_file(TRENDS_PATH)
    if data is None:
        return {}, "Aucune tendance précalculée. Lancez python -m src.jobs.refresh_all"

    if territoire and territoire in data:
        return data[territoire], None
    if "global" in data:
        return data["global"], None
    return data, None


def get_precomputed_dashboard(
    territoire: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Retourne les données de dashboard précalculées.

    Args:
        territoire: Territoire cible ou None pour global.

    Returns:
        Tuple (dashboard, message_erreur).
    """
    data = _load_json_file(DASHBOARDS_PATH)
    if data is None:
        return {}, "Aucun dashboard précalculé."

    if territoire and territoire in data:
        return data[territoire], None
    if "global" in data:
        return data["global"], None
    return data, None


def get_precomputed_matches(user_id: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Retourne les matchings précalculés pour un utilisateur.

    Args:
        user_id: Identifiant utilisateur.

    Returns:
        Tuple (matchings, message_erreur).
    """
    data = _load_json_file(MATCHES_PATH)
    if data is None:
        return [], "Aucun matching précalculé."

    user_matches = data.get(str(user_id)) or data.get(user_id) or []
    if not isinstance(user_matches, list):
        return [], "Format de matchings invalide."
    return user_matches, None


def get_territory_options() -> List[str]:
    """Retourne la liste des territoires disponibles.

    Returns:
        Liste triée des territoires.
    """
    offers, _ = get_precomputed_offers()
    territories = {
        str(o.get("territoire") or "").strip()
        for o in offers
        if isinstance(o, dict) and str(o.get("territoire") or "").strip()
    }
    return sorted(territories, key=str.lower)


def get_last_refresh_time() -> Optional[str]:
    """Retourne la date de dernière actualisation complète.

    Returns:
        Date ISO ou None.
    """
    return task_status.get_last_refresh()


def is_refresh_running() -> bool:
    """Indique si une actualisation est en cours.

    Returns:
        True si en cours.
    """
    return task_status.is_task_running("import_offers") or task_status.is_task_running("normalize_offers")


def get_cache_status() -> Dict[str, Any]:
    """Retourne le statut complet du cache.

    Returns:
        Dictionnaire de statut.
    """
    last_refresh = get_last_refresh_time()
    refresh_running = is_refresh_running()
    cache_stats = cache_store.get_status()

    offers_exist = ENRICHED_OFFERS_PATH.exists() or NORMALIZED_OFFERS_PATH.exists()
    trends_exist = TRENDS_PATH.exists()
    dashboards_exist = DASHBOARDS_PATH.exists()
    matches_exist = MATCHES_PATH.exists()

    offers_count = 0
    if ENRICHED_OFFERS_PATH.exists():
        data = _load_json_file(ENRICHED_OFFERS_PATH)
        if isinstance(data, list):
            offers_count = len(data)
    elif NORMALIZED_OFFERS_PATH.exists():
        data = _load_json_file(NORMALIZED_OFFERS_PATH)
        if isinstance(data, list):
            offers_count = len(data)

    return {
        "last_refresh": last_refresh,
        "refresh_running": refresh_running,
        "offers_available": offers_exist,
        "offers_count": offers_count,
        "trends_available": trends_exist,
        "dashboards_available": dashboards_exist,
        "matches_available": matches_exist,
        "cache_entries": cache_stats.get("total_entries", 0),
        "cache_size_bytes": cache_stats.get("total_size_bytes", 0),
    }


def has_precomputed_data() -> bool:
    """Indique si des données précalculées sont disponibles.

    Returns:
        True si au moins les offres existent.
    """
    return ENRICHED_OFFERS_PATH.exists() or NORMALIZED_OFFERS_PATH.exists()
