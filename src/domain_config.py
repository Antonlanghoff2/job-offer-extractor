# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Configuration des domaines métiers pour la collecte multi-métiers.

Ce module charge et gère la configuration des domaines métiers depuis
config/job_domains.json. Il permet de collecter des offres de tous
les secteurs, pas seulement l'IA et la Data.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "job_domains.json"


def load_job_domains() -> List[Dict[str, Any]]:
    """Charge la configuration des domaines métiers.

    Returns:
        Liste des domaines métiers configurés.

    Raises:
        FileNotFoundError: Si le fichier de configuration n'existe pas.
        json.JSONDecodeError: Si le fichier est mal formé.
    """
    if not CONFIG_PATH.exists():
        logger.warning(
            "Fichier de configuration des domaines introuvable: %s. "
            "Utilisation de la configuration par défaut.",
            CONFIG_PATH,
        )
        return _default_domains()

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            domains = json.load(f)
        if not isinstance(domains, list):
            raise ValueError("Le fichier de configuration doit contenir une liste.")
        return domains
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Erreur de chargement de la configuration: %s", exc)
        return _default_domains()


def _default_domains() -> List[Dict[str, Any]]:
    """Retourne une configuration par défaut minimale.

    Returns:
        Liste de domaines par défaut.
    """
    return [
        {
            "id": "general",
            "name": "Tous métiers",
            "enabled": True,
            "queries": [],
            "rome_codes": [],
            "priority": 0,
        }
    ]


def get_enabled_domains() -> List[Dict[str, Any]]:
    """Retourne les domaines activés.

    Returns:
        Liste des domaines activés, triés par priorité.
    """
    domains = load_job_domains()
    enabled = [d for d in domains if d.get("enabled", True)]
    return sorted(enabled, key=lambda d: d.get("priority", 999))


def get_all_queries() -> List[str]:
    """Retourne toutes les requêtes de collecte des domaines activés.

    Returns:
        Liste de requêtes dédupliquées.
    """
    domains = get_enabled_domains()
    queries = []
    seen = set()
    for domain in domains:
        for query in domain.get("queries", []):
            if query and query not in seen:
                queries.append(query)
                seen.add(query)
    return queries


def get_domain_by_id(domain_id: str) -> Optional[Dict[str, Any]]:
    """Retourne un domaine par son identifiant.

    Args:
        domain_id: Identifiant du domaine.

    Returns:
        Domaine trouvé ou None.
    """
    domains = load_job_domains()
    for domain in domains:
        if domain.get("id") == domain_id:
            return domain
    return None


def get_domain_names() -> List[str]:
    """Retourne les noms de tous les domaines activés.

    Returns:
        Liste des noms de domaines.
    """
    return [d.get("name", "") for d in get_enabled_domains() if d.get("name")]


def count_domains() -> int:
    """Retourne le nombre de domaines activés.

    Returns:
        Nombre de domaines activés.
    """
    return len(get_enabled_domains())
