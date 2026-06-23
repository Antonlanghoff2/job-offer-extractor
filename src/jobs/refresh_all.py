# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tâche principale de rafraîchissement complet.

Ce module orchestre toutes les étapes de précalcul :
1. Import des nouvelles offres
2. Normalisation
3. Extraction des données
4. Agrégation des tendances
5. Calcul des tableaux de bord
6. Calcul des matchings
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .cache import cache_store, compute_hash
from .locking import FileLock, LockError
from .status import task_status

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_import_offers() -> Dict[str, Any]:
    """Importe les nouvelles offres depuis France Travail.

    Returns:
        Statistiques de l'import.
    """
    from .import_offers import import_latest_offers
    
    task_status.update_task(
        "import_offers",
        "running",
        started_at=datetime.now().isoformat(),
    )
    
    try:
        stats = import_latest_offers()
        
        task_status.update_task(
            "import_offers",
            "success",
            completed_at=datetime.now().isoformat(),
            stats=stats,
        )
        
        return stats
    except Exception as e:
        task_status.update_task(
            "import_offers",
            "error",
            completed_at=datetime.now().isoformat(),
            error=str(e),
        )
        logger.error(f"Erreur import offres: {e}")
        raise


def run_normalize_offers() -> Dict[str, Any]:
    """Normalise toutes les offres.

    Returns:
        Statistiques de la normalisation.
    """
    from .normalize_offers import normalize_all_offers
    
    task_status.update_task(
        "normalize_offers",
        "running",
        started_at=datetime.now().isoformat(),
    )
    
    try:
        stats = normalize_all_offers()
        
        task_status.update_task(
            "normalize_offers",
            "success",
            completed_at=datetime.now().isoformat(),
            stats=stats,
        )
        
        return stats
    except Exception as e:
        task_status.update_task(
            "normalize_offers",
            "error",
            completed_at=datetime.now().isoformat(),
            error=str(e),
        )
        logger.error(f"Erreur normalisation: {e}")
        raise


def run_extract_offer_data() -> Dict[str, Any]:
    """Extrait les données de toutes les offres.

    Returns:
        Statistiques de l'extraction.
    """
    from .extract_offer_data import extract_all_offer_data
    
    task_status.update_task(
        "extract_offer_data",
        "running",
        started_at=datetime.now().isoformat(),
    )
    
    try:
        stats = extract_all_offer_data()
        
        task_status.update_task(
            "extract_offer_data",
            "success",
            completed_at=datetime.now().isoformat(),
            stats=stats,
        )
        
        return stats
    except Exception as e:
        task_status.update_task(
            "extract_offer_data",
            "error",
            completed_at=datetime.now().isoformat(),
            error=str(e),
        )
        logger.error(f"Erreur extraction: {e}")
        raise


def run_aggregate_trends() -> Dict[str, Any]:
    """Agrège les tendances du marché.

    Returns:
        Statistiques de l'agrégation.
    """
    from .aggregate_trends import aggregate_all_trends
    
    task_status.update_task(
        "aggregate_trends",
        "running",
        started_at=datetime.now().isoformat(),
    )
    
    try:
        stats = aggregate_all_trends()
        
        task_status.update_task(
            "aggregate_trends",
            "success",
            completed_at=datetime.now().isoformat(),
            stats=stats,
        )
        
        return stats
    except Exception as e:
        task_status.update_task(
            "aggregate_trends",
            "error",
            completed_at=datetime.now().isoformat(),
            error=str(e),
        )
        logger.error(f"Erreur agrégation: {e}")
        raise


def run_compute_dashboards() -> Dict[str, Any]:
    """Calcule les données des tableaux de bord.

    Returns:
        Statistiques du calcul.
    """
    from .compute_dashboards import compute_all_dashboards
    
    task_status.update_task(
        "compute_dashboards",
        "running",
        started_at=datetime.now().isoformat(),
    )
    
    try:
        stats = compute_all_dashboards()
        
        task_status.update_task(
            "compute_dashboards",
            "success",
            completed_at=datetime.now().isoformat(),
            stats=stats,
        )
        
        return stats
    except Exception as e:
        task_status.update_task(
            "compute_dashboards",
            "error",
            completed_at=datetime.now().isoformat(),
            error=str(e),
        )
        logger.error(f"Erreur calcul dashboards: {e}")
        raise


def run_compute_matches() -> Dict[str, Any]:
    """Calcule les matchings pour tous les profils.

    Returns:
        Statistiques du calcul.
    """
    from .compute_matches import compute_all_matches
    
    task_status.update_task(
        "compute_matches",
        "running",
        started_at=datetime.now().isoformat(),
    )
    
    try:
        stats = compute_all_matches()
        
        task_status.update_task(
            "compute_matches",
            "success",
            completed_at=datetime.now().isoformat(),
            stats=stats,
        )
        
        return stats
    except Exception as e:
        task_status.update_task(
            "compute_matches",
            "error",
            completed_at=datetime.now().isoformat(),
            error=str(e),
        )
        logger.error(f"Erreur calcul matchings: {e}")
        raise


def refresh_all() -> Dict[str, Any]:
    """Exécute toutes les étapes de rafraîchissement.

    Returns:
        Statistiques globales.
    """
    lock = FileLock("refresh_all")
    
    try:
        if not lock.acquire(blocking=False):
            logger.warning("Rafraîchissement déjà en cours")
            return {"status": "already_running"}
    except LockError:
        logger.warning("Rafraîchissement déjà en cours")
        return {"status": "already_running"}
    
    try:
        start_time = time.time()
        logger.info("Démarrage du rafraîchissement complet")
        
        stats = {
            "started_at": datetime.now().isoformat(),
            "steps": {},
        }
        
        # Étape 1: Import
        logger.info("Étape 1/6: Import des offres")
        step_start = time.time()
        stats["steps"]["import"] = run_import_offers()
        stats["steps"]["import"]["duration"] = time.time() - step_start
        
        # Étape 2: Normalisation
        logger.info("Étape 2/6: Normalisation")
        step_start = time.time()
        stats["steps"]["normalize"] = run_normalize_offers()
        stats["steps"]["normalize"]["duration"] = time.time() - step_start
        
        # Étape 3: Extraction
        logger.info("Étape 3/6: Extraction des données")
        step_start = time.time()
        stats["steps"]["extract"] = run_extract_offer_data()
        stats["steps"]["extract"]["duration"] = time.time() - step_start
        
        # Étape 4: Agrégation
        logger.info("Étape 4/6: Agrégation des tendances")
        step_start = time.time()
        stats["steps"]["aggregate"] = run_aggregate_trends()
        stats["steps"]["aggregate"]["duration"] = time.time() - step_start
        
        # Étape 5: Dashboards
        logger.info("Étape 5/6: Calcul des tableaux de bord")
        step_start = time.time()
        stats["steps"]["dashboards"] = run_compute_dashboards()
        stats["steps"]["dashboards"]["duration"] = time.time() - step_start
        
        # Étape 6: Matchings
        logger.info("Étape 6/6: Calcul des matchings")
        step_start = time.time()
        stats["steps"]["matches"] = run_compute_matches()
        stats["steps"]["matches"]["duration"] = time.time() - step_start
        
        stats["completed_at"] = datetime.now().isoformat()
        stats["total_duration"] = time.time() - start_time
        stats["status"] = "success"
        
        task_status.mark_refresh_complete()
        
        logger.info(f"Rafraîchissement terminé en {stats['total_duration']:.2f}s")
        
        return stats
        
    except Exception as e:
        logger.error(f"Erreur rafraîchissement: {e}")
        stats["status"] = "error"
        stats["error"] = str(e)
        return stats
        
    finally:
        lock.release()


def main():
    """Point d'entrée principal."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    stats = refresh_all()
    
    if stats.get("status") == "success":
        print(f"✓ Rafraîchissement terminé en {stats['total_duration']:.2f}s")
        sys.exit(0)
    elif stats.get("status") == "already_running":
        print("⚠ Rafraîchissement déjà en cours")
        sys.exit(0)
    else:
        print(f"✗ Erreur: {stats.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
