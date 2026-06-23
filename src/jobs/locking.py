# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Verrouillage pour éviter les exécutions simultanées.

Ce module fournit un mécanisme de verrouillage par fichier pour empêcher
plusieurs instances de tâches de s'exécuter en parallèle.
"""

from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCK_DIR = PROJECT_ROOT / "data" / "locks"


class LockError(Exception):
    """Exception levée lorsqu'un verrou ne peut être acquis."""
    pass


class FileLock:
    """Verrou par fichier utilisant fcntl."""

    def __init__(self, name: str, lock_dir: Optional[Path] = None):
        """Initialise le verrou.

        Args:
            name: Nom du verrou.
            lock_dir: Répertoire des verrous.
        """
        self.name = name
        self.lock_dir = lock_dir or LOCK_DIR
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.lock_dir / f"{name}.lock"
        self.lock_file: Optional[object] = None

    def acquire(self, blocking: bool = False) -> bool:
        """Acquiert le verrou.

        Args:
            blocking: Si True, attend jusqu'à obtenir le verrou.

        Returns:
            True si le verrou a été acquis, False sinon.

        Raises:
            LockError: Si le verrou ne peut être acquis et blocking=False.
        """
        try:
            self.lock_file = open(self.lock_path, "w")
            
            if blocking:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
                return True
            else:
                try:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except (IOError, OSError):
                    self.lock_file.close()
                    self.lock_file = None
                    return False
        except OSError as e:
            logger.error(f"Erreur acquisition verrou {self.name}: {e}")
            raise LockError(f"Impossible d'acquérir le verrou: {e}")

    def release(self) -> None:
        """Libère le verrou."""
        if self.lock_file is not None:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                self.lock_file = None
                if self.lock_path.exists():
                    self.lock_path.unlink()
            except OSError as e:
                logger.error(f"Erreur libération verrou {self.name}: {e}")

    def is_locked(self) -> bool:
        """Vérifie si le verrou est actif.

        Returns:
            True si le verrou est actif.
        """
        if not self.lock_path.exists():
            return False
        
        try:
            with open(self.lock_path, "w") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    return False
                except (IOError, OSError):
                    return True
        except OSError:
            return False

    def __enter__(self) -> "FileLock":
        """Context manager: acquisition du verrou."""
        if not self.acquire(blocking=False):
            raise LockError(f"Verrou {self.name} déjà actif")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager: libération du verrou."""
        self.release()


def with_lock(name: str):
    """Décorateur pour exécuter une fonction avec un verrou.

    Args:
        name: Nom du verrou.

    Returns:
        Décorateur.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            lock = FileLock(name)
            try:
                with lock:
                    return func(*args, **kwargs)
            except LockError:
                logger.warning(f"Tâche {name} déjà en cours d'exécution")
                return None
        return wrapper
    return decorator
