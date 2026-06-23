# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests de performance pour vérifier l'optimisation des routes.

Ces tests vérifient que :
1. Un rechargement de page ne déclenche aucun recalcul lourd
2. Une route de consultation n'appelle pas le modèle NLP
3. Une route de consultation ne parcourt pas toutes les offres
4. Les pages lisent le dernier cache valide
5. La pagination est appliquée avant chargement massif
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import Mock, patch, MagicMock

from src.web_app import create_app
from src.cache_reader import has_precomputed_data, get_precomputed_offers


class PerformanceTest(unittest.TestCase):
    """Tests de performance des routes Flask."""

    def setUp(self) -> None:
        self.app = create_app()
        self.client = self.app.test_client()

    @patch("src.web_app.has_precomputed_data", return_value=True)
    @patch("src.web_app.get_precomputed_offers")
    @patch("src.web_app.get_precomputed_trends")
    @patch("src.web_app.get_cached_territory_options", return_value=[])
    @patch("src.web_app.load_market_context_rows", return_value=[])
    def test_cached_route_does_not_call_nlp(
        self,
        mock_context: Mock,
        mock_territory: Mock,
        mock_trends: Mock,
        mock_offers: Mock,
        mock_cache: Mock,
    ) -> None:
        """Vérifie qu'une route avec cache n'appelle pas le NLP."""
        mock_offers.return_value = ([], None)
        mock_trends.return_value = ({}, None)

        with patch("src.web_app.extract_skills_from_offer") as mock_extract:
            response = self.client.get("/?mots_cles=python")
            self.assertEqual(response.status_code, 200)
            mock_extract.assert_not_called()

    @patch("src.web_app.has_precomputed_data", return_value=True)
    @patch("src.web_app.get_precomputed_offers")
    @patch("src.web_app.get_precomputed_trends")
    @patch("src.web_app.get_cached_territory_options", return_value=[])
    @patch("src.web_app.load_market_context_rows", return_value=[])
    def test_cached_route_does_not_call_aggregate_trends(
        self,
        mock_context: Mock,
        mock_territory: Mock,
        mock_trends: Mock,
        mock_offers: Mock,
        mock_cache: Mock,
    ) -> None:
        """Vérifie qu'une route avec cache n'appelle pas aggregate_trends."""
        mock_offers.return_value = ([], None)
        mock_trends.return_value = ({}, None)

        with patch("src.web_app.aggregate_trends") as mock_aggregate:
            response = self.client.get("/?mots_cles=python")
            self.assertEqual(response.status_code, 200)
            mock_aggregate.assert_not_called()

    @patch("src.web_app.has_precomputed_data", return_value=True)
    @patch("src.web_app.get_precomputed_offers")
    @patch("src.web_app.get_precomputed_trends")
    @patch("src.web_app.get_cached_territory_options", return_value=[])
    @patch("src.web_app.load_market_context_rows", return_value=[])
    def test_cached_route_does_not_call_compute_match(
        self,
        mock_context: Mock,
        mock_territory: Mock,
        mock_trends: Mock,
        mock_offers: Mock,
        mock_cache: Mock,
    ) -> None:
        """Vérifie qu'une route avec cache n'appelle pas compute_match."""
        mock_offers.return_value = ([], None)
        mock_trends.return_value = ({}, None)

        with patch("src.web_app.compute_match") as mock_match:
            response = self.client.get("/?mots_cles=python")
            self.assertEqual(response.status_code, 200)
            mock_match.assert_not_called()

    @patch("src.web_app.has_precomputed_data", return_value=True)
    @patch("src.web_app.get_precomputed_offers")
    @patch("src.web_app.get_precomputed_trends")
    @patch("src.web_app.get_cached_territory_options", return_value=[])
    @patch("src.web_app.load_market_context_rows", return_value=[])
    def test_pagination_limits_offers_loaded(
        self,
        mock_context: Mock,
        mock_territory: Mock,
        mock_trends: Mock,
        mock_offers: Mock,
        mock_cache: Mock,
    ) -> None:
        """Vérifie que la pagination limite les offres chargées."""
        offers = [{"id": str(i), "intitule": f"Offre {i}", "territoire": "Lyon"} for i in range(1000)]
        mock_offers.return_value = (offers, None)
        mock_trends.return_value = ({}, None)

        response = self.client.get("/?mots_cles=Offre&territoire_type=all&per_page=10&page=1")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Page 1 /", body)

    @patch("src.user_portal.has_precomputed_data", return_value=True)
    @patch("src.user_portal.get_precomputed_matches")
    @patch("src.user_portal.get_precomputed_offers")
    @patch("src.user_portal._current_user_id", return_value=1)
    @patch("src.user_portal.login_required", lambda f: f)
    def test_recommendations_reads_cache(
        self,
        mock_user_id: Mock,
        mock_offers: Mock,
        mock_matches: Mock,
        mock_cache: Mock,
    ) -> None:
        """Vérifie que /mes-offres lit le cache."""
        mock_matches.return_value = ([{"offer_id": "1", "score": 80.0, "details": {}}], None)
        mock_offers.return_value = ([{"id": "1", "titre": "Test"}], None)

        with patch("src.user_portal.compute_match") as mock_compute:
            response = self.client.get("/mes-offres")
            mock_compute.assert_not_called()

    def test_cache_reader_returns_status(self) -> None:
        """Vérifie que le cache reader retourne un statut."""
        from src.cache_reader import get_cache_status
        status = get_cache_status()
        self.assertIn("offers_available", status)
        self.assertIn("trends_available", status)
        self.assertIn("matches_available", status)

    def test_has_precomputed_data_checks_files(self) -> None:
        """Vérifie que has_precomputed_data vérifie les fichiers."""
        result = has_precomputed_data()
        self.assertIsInstance(result, bool)


class LockingTest(unittest.TestCase):
    """Tests du verrouillage des tâches."""

    def test_file_lock_prevents_concurrent_execution(self) -> None:
        """Vérifie que le verrou empêche l'exécution simultanée."""
        from src.jobs.locking import FileLock, LockError

        lock1 = FileLock("test_lock")
        lock2 = FileLock("test_lock")

        try:
            acquired1 = lock1.acquire(blocking=False)
            self.assertTrue(acquired1)

            acquired2 = lock2.acquire(blocking=False)
            self.assertFalse(acquired2)
        finally:
            lock1.release()

    def test_file_lock_releases_properly(self) -> None:
        """Vérifie que le verrou se libère correctement."""
        from src.jobs.locking import FileLock

        lock = FileLock("test_lock_release")
        try:
            lock.acquire(blocking=False)
            lock.release()

            lock2 = FileLock("test_lock_release")
            acquired = lock2.acquire(blocking=False)
            self.assertTrue(acquired)
            lock2.release()
        finally:
            try:
                lock.release()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
