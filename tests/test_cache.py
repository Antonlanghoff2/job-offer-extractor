# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests pour le système de cache.

Ce module teste le fonctionnement du cache persistant.
"""

from __future__ import annotations

import pytest
from pathlib import Path
import tempfile
import shutil

from src.jobs.cache import CacheStore, compute_hash


class TestCacheStore:
    """Tests pour CacheStore."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Crée un répertoire de cache temporaire."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def cache(self, temp_cache_dir):
        """Crée une instance de CacheStore."""
        return CacheStore(temp_cache_dir)

    def test_set_and_get(self, cache):
        """Teste le stockage et la récupération."""
        cache.set("test_key", {"data": "value"}, input_hash="hash123")
        
        result = cache.get("test_key")
        assert result is not None
        assert result["value"] == {"data": "value"}
        assert result["input_hash"] == "hash123"
        assert "computed_at" in result

    def test_get_nonexistent(self, cache):
        """Teste la récupération d'une clé inexistante."""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_delete(self, cache):
        """Teste la suppression."""
        cache.set("test_key", {"data": "value"})
        cache.delete("test_key")
        
        result = cache.get("test_key")
        assert result is None

    def test_invalidate_by_prefix(self, cache):
        """Teste l'invalidation par préfixe."""
        cache.set("offer:1", {"data": "value1"})
        cache.set("offer:2", {"data": "value2"})
        cache.set("trend:1", {"data": "value3"})
        
        count = cache.invalidate_by_prefix("offer:")
        assert count == 2
        
        assert cache.get("offer:1") is None
        assert cache.get("offer:2") is None
        assert cache.get("trend:1") is not None

    def test_clear_all(self, cache):
        """Teste la suppression de toutes les entrées."""
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})
        
        cache.clear_all()
        
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_get_status(self, cache):
        """Teste la récupération du statut."""
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})
        
        status = cache.get_status()
        assert status["total_entries"] == 2
        assert status["total_size_bytes"] > 0


class TestComputeHash:
    """Tests pour compute_hash."""

    def test_hash_dict(self):
        """Teste le hash d'un dictionnaire."""
        data = {"key": "value", "number": 42}
        hash1 = compute_hash(data)
        hash2 = compute_hash(data)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256

    def test_hash_different_data(self):
        """Teste que des données différentes produisent des hash différents."""
        hash1 = compute_hash({"key": "value1"})
        hash2 = compute_hash({"key": "value2"})
        
        assert hash1 != hash2

    def test_hash_order_independent(self):
        """Teste que l'ordre des clés n'importe pas."""
        hash1 = compute_hash({"a": 1, "b": 2})
        hash2 = compute_hash({"b": 2, "a": 1})
        
        assert hash1 == hash2
