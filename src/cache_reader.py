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
from src.territory_normalization import find_territory_key_in_data, is_territory_debug_mode

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"

ENRICHED_OFFERS_PATH = DATA_PROCESSED / "offres_enrichies.json"
NORMALIZED_OFFERS_PATH = DATA_PROCESSED / "offres_normalisees.json"
TRENDS_PATH = DATA_PROCESSED / "trends.json"
DASHBOARDS_PATH = DATA_PROCESSED / "dashboards.json"
MATCHES_PATH = DATA_PROCESSED / "matches.json"

CACHE_SCHEMA_VERSION = 2
CACHE_SCHEMA_VERSION_PATH = DATA_PROCESSED / ".cache_schema_version"


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

    if not territoire:
        if "global" in data:
            return data["global"], None
        return data, None

    matched_key = find_territory_key_in_data(territoire, data.keys())

    if is_territory_debug_mode():
        logger.info(
            "territory_raw=%r territory_matched=%r available_keys=%d",
            territoire,
            matched_key,
            len(data),
        )

    if matched_key and matched_key in data:
        return data[matched_key], None

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

    if not territoire:
        if "global" in data:
            return data["global"], None
        return data, None

    matched_key = find_territory_key_in_data(territoire, data.keys())

    if is_territory_debug_mode():
        logger.info(
            "dashboard_territory_raw=%r dashboard_territory_matched=%r available_keys=%d",
            territoire,
            matched_key,
            len(data),
        )

    if matched_key and matched_key in data:
        return data[matched_key], None

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


def get_cache_schema_version() -> int:
    """Retourne la version du schéma de cache stockée.

    Returns:
        Version du schéma (0 si absente).
    """
    if not CACHE_SCHEMA_VERSION_PATH.exists():
        return 0
    try:
        text = CACHE_SCHEMA_VERSION_PATH.read_text(encoding="utf-8").strip()
        return int(text)
    except (ValueError, OSError):
        return 0


def write_cache_schema_version(version: int = CACHE_SCHEMA_VERSION) -> None:
    """Écrit la version courante du schéma de cache.

    Args:
        version: Version à écrire.
    """
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    CACHE_SCHEMA_VERSION_PATH.write_text(str(version), encoding="utf-8")


def is_cache_schema_valid() -> bool:
    """Vérifie si le cache est compatible avec le schéma courant.

    Returns:
        True si la version du cache correspond.
    """
    return get_cache_schema_version() >= CACHE_SCHEMA_VERSION


def invalidate_cache_if_needed() -> bool:
    """Invalide les fichiers de cache si le schéma a changé.

    Returns:
        True si le cache a été invalidé.
    """
    if is_cache_schema_valid():
        return False
    old_version = get_cache_schema_version()
    logger.warning(
        "Schema de cache obsolete (v%s < v%s). Invalidation des fichiers.",
        old_version,
        CACHE_SCHEMA_VERSION,
    )
    for path in (ENRICHED_OFFERS_PATH, NORMALIZED_OFFERS_PATH, TRENDS_PATH, DASHBOARDS_PATH, MATCHES_PATH):
        if path.exists():
            try:
                path.unlink()
                logger.info("Fichier invalide supprime: %s", path)
            except OSError as exc:
                logger.error("Erreur suppression %s: %s", path, exc)
    write_cache_schema_version()
    return True
