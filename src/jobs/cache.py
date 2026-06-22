# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Système de cache persistant pour TrendRadar IA.

Ce module fournit un stockage persistant pour toutes les données précalculées.
Chaque entrée contient des métadonnées de versioning pour l'invalidation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"


class CacheStore:
    """Stockage persistant pour les données précalculées."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialise le cache.

        Args:
            cache_dir: Répertoire de stockage du cache.
        """
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """Retourne le chemin du fichier de cache pour une clé."""
        safe_key = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Récupère une entrée du cache.

        Args:
            key: Clé de l'entrée.

        Returns:
            Données de l'entrée ou None si absente/expirée.
        """
        path = self._get_path(key)
        if not path.exists():
            return None

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Erreur lecture cache {key}: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        input_hash: str = "",
        source_version: str = "",
        model_version: str = "",
    ) -> None:
        """Stocke une entrée dans le cache.

        Args:
            key: Clé de l'entrée.
            value: Données à stocker.
            input_hash: Hash des données d'entrée.
            source_version: Version de la source.
            model_version: Version du modèle.
        """
        path = self._get_path(key)
        data = {
            "key": key,
            "value": value,
            "computed_at": datetime.now().isoformat(),
            "input_hash": input_hash,
            "source_version": source_version,
            "model_version": model_version,
            "status": "success",
        }

        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"Erreur écriture cache {key}: {e}")

    def delete(self, key: str) -> None:
        """Supprime une entrée du cache.

        Args:
            key: Clé de l'entrée.
        """
        path = self._get_path(key)
        if path.exists():
            try:
                path.unlink()
            except OSError as e:
                logger.error(f"Erreur suppression cache {key}: {e}")

    def invalidate_by_prefix(self, prefix: str) -> int:
        """Invalide toutes les entrées dont la clé commence par le préfixe.

        Args:
            prefix: Préfixe des clés à invalider.

        Returns:
            Nombre d'entrées invalidées.
        """
        count = 0
        for path in self.cache_dir.glob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("key", "").startswith(prefix):
                    path.unlink()
                    count += 1
            except (json.JSONDecodeError, OSError):
                continue
        return count

    def clear_all(self) -> None:
        """Supprime toutes les entrées du cache."""
        for path in self.cache_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError as e:
                logger.error(f"Erreur suppression {path}: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Retourne le statut du cache.

        Returns:
            Statistiques du cache.
        """
        stats = {
            "total_entries": 0,
            "total_size_bytes": 0,
            "oldest_entry": None,
            "newest_entry": None,
        }

        for path in self.cache_dir.glob("*.json"):
            try:
                stats["total_entries"] += 1
                stats["total_size_bytes"] += path.stat().st_size

                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                computed_at = data.get("computed_at")
                if computed_at:
                    if stats["oldest_entry"] is None or computed_at < stats["oldest_entry"]:
                        stats["oldest_entry"] = computed_at
                    if stats["newest_entry"] is None or computed_at > stats["newest_entry"]:
                        stats["newest_entry"] = computed_at
            except (json.JSONDecodeError, OSError):
                continue

        return stats


def compute_hash(data: Any) -> str:
    """Calcule le hash SHA256 d'une donnée.

    Args:
        data: Données à hasher.

    Returns:
        Hash SHA256 en hexadécimal.
    """
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


# Instance globale du cache
cache_store = CacheStore()
