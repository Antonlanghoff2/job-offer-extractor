# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Statut des tâches de précalcul.

Ce module permet de suivre l'état d'avancement des tâches de précalcul
et de fournir des informations aux interfaces utilisateur.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATUS_DIR = PROJECT_ROOT / "data" / "status"


class TaskStatus:
    """Gestionnaire de statut des tâches."""

    def __init__(self, status_dir: Optional[Path] = None):
        """Initialise le gestionnaire de statut.

        Args:
            status_dir: Répertoire de stockage des statuts.
        """
        self.status_dir = status_dir or STATUS_DIR
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = self.status_dir / "tasks_status.json"

    def _load_status(self) -> Dict[str, Any]:
        """Charge le fichier de statut.

        Returns:
            Données de statut.
        """
        if not self.status_file.exists():
            return {"tasks": {}, "last_refresh": None}

        try:
            with self.status_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Erreur lecture statut: {e}")
            return {"tasks": {}, "last_refresh": None}

    def _save_status(self, data: Dict[str, Any]) -> None:
        """Sauvegarde le fichier de statut.

        Args:
            data: Données de statut.
        """
        try:
            with self.status_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"Erreur écriture statut: {e}")

    def update_task(
        self,
        task_name: str,
        status: str,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        error: Optional[str] = None,
        stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Met à jour le statut d'une tâche.

        Args:
            task_name: Nom de la tâche.
            status: Statut (running, success, error).
            started_at: Date de début.
            completed_at: Date de fin.
            error: Message d'erreur.
            stats: Statistiques de la tâche.
        """
        data = self._load_status()

        if task_name not in data["tasks"]:
            data["tasks"][task_name] = {}

        task = data["tasks"][task_name]
        task["status"] = status

        if started_at:
            task["started_at"] = started_at
        if completed_at:
            task["completed_at"] = completed_at
        if error:
            task["error"] = error
        elif "error" in task:
            del task["error"]
        if stats:
            task["stats"] = stats

        if status == "success":
            data["last_refresh"] = datetime.now().isoformat()

        self._save_status(data)

    def get_task_status(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Retourne le statut d'une tâche.

        Args:
            task_name: Nom de la tâche.

        Returns:
            Statut de la tâche ou None.
        """
        data = self._load_status()
        return data["tasks"].get(task_name)

    def get_all_status(self) -> Dict[str, Any]:
        """Retourne le statut de toutes les tâches.

        Returns:
            Statut complet.
        """
        return self._load_status()

    def is_task_running(self, task_name: str) -> bool:
        """Vérifie si une tâche est en cours d'exécution.

        Args:
            task_name: Nom de la tâche.

        Returns:
            True si la tâche est en cours.
        """
        task = self.get_task_status(task_name)
        return task is not None and task.get("status") == "running"

    def get_last_refresh(self) -> Optional[str]:
        """Retourne la date de dernière actualisation complète.

        Returns:
            Date ISO ou None.
        """
        data = self._load_status()
        return data.get("last_refresh")

    def mark_refresh_complete(self) -> None:
        """Marque l'actualisation complète comme terminée."""
        data = self._load_status()
        data["last_refresh"] = datetime.now().isoformat()
        self._save_status(data)

    def add_error(self, task_name: str, offer_id: str, step: str, error: str) -> None:
        """Ajoute une erreur au log.

        Args:
            task_name: Nom de la tâche.
            offer_id: Identifiant de l'offre.
            step: Étape en erreur.
            error: Message d'erreur.
        """
        errors_file = self.status_dir / "errors.log"
        try:
            with errors_file.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()}|{task_name}|{offer_id}|{step}|{error}\n")
        except OSError as e:
            logger.error(f"Erreur écriture log erreurs: {e}")

    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, str]]:
        """Retourne les erreurs récentes.

        Args:
            limit: Nombre maximum d'erreurs.

        Returns:
            Liste des erreurs.
        """
        errors_file = self.status_dir / "errors.log"
        if not errors_file.exists():
            return []

        errors = []
        try:
            with errors_file.open("r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    parts = line.strip().split("|")
                    if len(parts) >= 5:
                        errors.append({
                            "timestamp": parts[0],
                            "task": parts[1],
                            "offer_id": parts[2],
                            "step": parts[3],
                            "error": parts[4],
                        })
        except OSError as e:
            logger.error(f"Erreur lecture log erreurs: {e}")

        return list(reversed(errors))


# Instance globale
task_status = TaskStatus()
