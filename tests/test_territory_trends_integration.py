# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests d'intégration Flask pour le filtrage territorial."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from src.web_app import create_app


class TerritoryTrendsIntegrationTest(unittest.TestCase):
    """Tests d'intégration pour la page Tendances par territoire."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.test_dir) / "data" / "processed"
        self.data_dir.mkdir(parents=True)

        self.offers = [
            {
                "id": "1",
                "intitule": "Dev Python Paris",
                "territoire": "75 - Paris",
                "ville": "Paris",
                "code_postal": "75001",
                "competences": ["Python", "Flask"],
                "source": "France Travail",
            },
            {
                "id": "2",
                "intitule": "Dev Python Paris 2",
                "territoire": "75 - Paris",
                "ville": "Paris",
                "code_postal": "75002",
                "competences": ["Python", "Django"],
                "source": "France Travail",
            },
            {
                "id": "3",
                "intitule": "Dev Python Lyon",
                "territoire": "69 - Lyon",
                "ville": "Lyon",
                "code_postal": "69001",
                "competences": ["Python", "FastAPI"],
                "source": "France Travail",
            },
            {
                "id": "4",
                "intitule": "Dev Java Marseille",
                "territoire": "13 - Marseille",
                "ville": "Marseille",
                "code_postal": "13001",
                "competences": ["Java", "Spring"],
                "source": "France Travail",
            },
        ]

        self.trends = {
            "global": {
                "nombre_offres": 4,
                "competences": {
                    "Python": 3,
                    "Flask": 1,
                    "Django": 1,
                    "FastAPI": 1,
                    "Java": 1,
                    "Spring": 1,
                },
            },
            "75 - Paris": {
                "nombre_offres": 2,
                "competences": {
                    "Python": 2,
                    "Flask": 1,
                    "Django": 1,
                },
            },
            "69 - Lyon": {
                "nombre_offres": 1,
                "competences": {
                    "Python": 1,
                    "FastAPI": 1,
                },
            },
        }

        offers_path = self.data_dir / "offres_enrichies.json"
        trends_path = self.data_dir / "trends.json"

        with offers_path.open("w") as f:
            json.dump(self.offers, f)
        with trends_path.open("w") as f:
            json.dump(self.trends, f)

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("src.web_app.PROJECT_ROOT")
    def test_no_territory_shows_all_offers(self, mock_root: Any) -> None:
        mock_root.__truediv__ = lambda self, x: Path(self.test_dir) / x
        with patch("src.cache_reader.PROJECT_ROOT", Path(self.test_dir)):
            response = self.client.get("/tendances")
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertIn("4", body)

    @patch("src.web_app.PROJECT_ROOT")
    def test_paris_filters_offers(self, mock_root: Any) -> None:
        mock_root.__truediv__ = lambda self, x: Path(self.test_dir) / x
        with patch("src.cache_reader.PROJECT_ROOT", Path(self.test_dir)):
            response = self.client.get("/tendances?territoire=Paris")
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertIn("2", body)

    @patch("src.web_app.PROJECT_ROOT")
    def test_lyon_filters_offers(self, mock_root: Any) -> None:
        mock_root.__truediv__ = lambda self, x: Path(self.test_dir) / x
        with patch("src.cache_reader.PROJECT_ROOT", Path(self.test_dir)):
            response = self.client.get("/tendances?territoire=Lyon")
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertIn("1", body)

    @patch("src.web_app.PROJECT_ROOT")
    def test_department_code_filters_offers(self, mock_root: Any) -> None:
        mock_root.__truediv__ = lambda self, x: Path(self.test_dir) / x
        with patch("src.cache_reader.PROJECT_ROOT", Path(self.test_dir)):
            response = self.client.get("/tendances?territoire=75")
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertIn("2", body)

    @patch("src.web_app.PROJECT_ROOT")
    def test_different_territories_different_counts(self, mock_root: Any) -> None:
        mock_root.__truediv__ = lambda self, x: Path(self.test_dir) / x
        with patch("src.cache_reader.PROJECT_ROOT", Path(self.test_dir)):
            response_paris = self.client.get("/tendances?territoire=Paris")
            response_lyon = self.client.get("/tendances?territoire=Lyon")

            body_paris = response_paris.get_data(as_text=True)
            body_lyon = response_lyon.get_data(as_text=True)

            self.assertIn("2", body_paris)
            self.assertIn("1", body_lyon)

    @patch("src.web_app.PROJECT_ROOT")
    def test_selected_territory_displayed(self, mock_root: Any) -> None:
        mock_root.__truediv__ = lambda self, x: Path(self.test_dir) / x
        with patch("src.cache_reader.PROJECT_ROOT", Path(self.test_dir)):
            response = self.client.get("/tendances?territoire=Paris")
            body = response.get_data(as_text=True)
            self.assertIn("Paris", body)


if __name__ == "__main__":
    unittest.main()
