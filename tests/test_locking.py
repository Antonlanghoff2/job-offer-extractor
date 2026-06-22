# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests pour le système de verrouillage.

Ce module teste le fonctionnement du verrouillage par fichier.
"""

from __future__ import annotations

import pytest
from pathlib import Path
import tempfile
import shutil

from src.jobs.locking import FileLock, LockError


class TestFileLock:
    """Tests pour FileLock."""

    @pytest.fixture
    def temp_lock_dir(self):
        """Crée un répertoire de verrous temporaire."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def test_acquire_and_release(self, temp_lock_dir):
        """Teste l'acquisition et la libération."""
        lock = FileLock("test_lock", temp_lock_dir)
        
        assert lock.acquire(blocking=False)
        assert lock.is_locked()
        
        lock.release()
        assert not lock.is_locked()

    def test_context_manager(self, temp_lock_dir):
        """Teste l'utilisation comme context manager."""
        lock = FileLock("test_lock", temp_lock_dir)
        
        with lock:
            assert lock.is_locked()
        
        assert not lock.is_locked()

    def test_double_acquire_fails(self, temp_lock_dir):
        """Teste que deux acquisitions échouent."""
        lock1 = FileLock("test_lock", temp_lock_dir)
        lock2 = FileLock("test_lock", temp_lock_dir)
        
        assert lock1.acquire(blocking=False)
        
        with pytest.raises(LockError):
            with lock2:
                pass
        
        lock1.release()

    def test_different_locks_independent(self, temp_lock_dir):
        """Teste que des verrous différents sont indépendants."""
        lock1 = FileLock("lock1", temp_lock_dir)
        lock2 = FileLock("lock2", temp_lock_dir)
        
        assert lock1.acquire(blocking=False)
        assert lock2.acquire(blocking=False)
        
        lock1.release()
        lock2.release()

    def test_is_locked_without_acquire(self, temp_lock_dir):
        """Teste is_locked sans acquisition préalable."""
        lock = FileLock("test_lock", temp_lock_dir)
        
        assert not lock.is_locked()
