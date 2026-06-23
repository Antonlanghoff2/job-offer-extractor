# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests pour le système de statut.

Ce module teste le suivi de l'état des tâches.
"""

from __future__ import annotations

import pytest
from pathlib import Path
import tempfile
import shutil

from src.jobs.status import TaskStatus


class TestTaskStatus:
    """Tests pour TaskStatus."""

    @pytest.fixture
    def temp_status_dir(self):
        """Crée un répertoire de statut temporaire."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def status(self, temp_status_dir):
        """Crée une instance de TaskStatus."""
        return TaskStatus(temp_status_dir)

    def test_update_task_status(self, status):
        """Teste la mise à jour du statut."""
        status.update_task("test_task", "running", started_at="2024-01-01T00:00:00")
        
        task_status = status.get_task_status("test_task")
        assert task_status is not None
        assert task_status["status"] == "running"
        assert task_status["started_at"] == "2024-01-01T00:00:00"

    def test_update_task_completion(self, status):
        """Teste la mise à jour de la complétion."""
        status.update_task("test_task", "running", started_at="2024-01-01T00:00:00")
        status.update_task("test_task", "success", completed_at="2024-01-01T00:01:00")
        
        task_status = status.get_task_status("test_task")
        assert task_status["status"] == "success"
        assert task_status["completed_at"] == "2024-01-01T00:01:00"

    def test_update_task_error(self, status):
        """Teste la mise à jour d'une erreur."""
        status.update_task("test_task", "error", error="Something went wrong")
        
        task_status = status.get_task_status("test_task")
        assert task_status["status"] == "error"
        assert task_status["error"] == "Something went wrong"

    def test_is_task_running(self, status):
        """Teste la vérification d'exécution."""
        status.update_task("test_task", "running")
        
        assert status.is_task_running("test_task")
        
        status.update_task("test_task", "success")
        
        assert not status.is_task_running("test_task")

    def test_get_all_status(self, status):
        """Teste la récupération de tous les statuts."""
        status.update_task("task1", "running")
        status.update_task("task2", "success")
        
        all_status = status.get_all_status()
        assert "tasks" in all_status
        assert "task1" in all_status["tasks"]
        assert "task2" in all_status["tasks"]

    def test_mark_refresh_complete(self, status):
        """Teste le marquage de rafraîchissement complet."""
        status.mark_refresh_complete()
        
        last_refresh = status.get_last_refresh()
        assert last_refresh is not None

    def test_add_error(self, status):
        """Teste l'ajout d'erreur au log."""
        status.add_error("test_task", "offer_123", "extraction", "Error message")
        
        errors = status.get_recent_errors()
        assert len(errors) > 0
        assert errors[0]["task"] == "test_task"
        assert errors[0]["offer_id"] == "offer_123"
        assert errors[0]["step"] == "extraction"
        assert errors[0]["error"] == "Error message"

    def test_get_recent_errors_limit(self, status):
        """Teste la limite des erreurs récentes."""
        for i in range(10):
            status.add_error("test_task", f"offer_{i}", "extraction", f"Error {i}")
        
        errors = status.get_recent_errors(limit=5)
        assert len(errors) == 5
