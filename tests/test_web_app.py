# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Dict, List

import unittest
from unittest.mock import Mock, patch

from src.web_app import create_app


def make_raw_offers(territoire: str) -> List[Dict[str, object]]:
    return [
        {
            "id": "1",
            "intitule": "Développeur Python",
            "description": "Construire des outils IA.",
            "dateCreation": "2026-06-17T10:00:00Z",
            "territoire": territoire,
            "lieuTravail": {"libelle": territoire, "commune": territoire, "codePostal": territoire},
            "entreprise": {"nom": "ACME"},
            "typeContratLibelle": "CDI",
            "origineOffre": {"urlOrigine": "https://example.com/1"},
            "competences": [{"libelle": "Python"}],
        },
        {
            "id": "2",
            "intitule": "Data Engineer",
            "description": "Gérer la donnée.",
            "dateCreation": "2026-06-16T10:00:00Z",
            "territoire": territoire,
            "lieuTravail": {"libelle": territoire, "commune": territoire, "codePostal": territoire},
            "entreprise": {"nom": "Beta"},
            "typeContratLibelle": "CDD",
            "competences": [{"libelle": "SQL"}],
        },
    ]




class WebAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = self.app.test_client()

    @patch("src.web_app.load_raw_offers", return_value=make_raw_offers("ALL"))
    @patch("src.web_app.load_market_context_rows", return_value=[])
    @patch("src.web_app.iter_search_offres")
    def test_search_without_territory_and_pagination(self, mock_search: Mock, _mock_context: Mock, _mock_raw: Mock) -> None:
        mock_search.return_value = make_raw_offers("ALL")

        response = self.client.get("/?mots_cles=python&territoire_type=all&per_page=1&page=1")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("2 offres trouvées pour tous les territoires", body)
        self.assertIn("Page 1 / 2", body)
        self.assertIn("Suivant", body)
        self.assertIn("page=2", body)
        self.assertIn("selected", body)
        self.assertIn("Développeur Python", body)
        self.assertIn("Mon compte", body)
        self.assertIn("Mon profil", body)
        self.assertIn("Déconnexion", body)

    @patch("src.web_app.load_raw_offers", return_value=make_raw_offers("69123"))
    @patch("src.web_app.load_market_context_rows", return_value=[])
    @patch("src.web_app.iter_search_offres")
    def test_commune_search_forwards_filters(self, mock_search: Mock, _mock_context: Mock, _mock_raw: Mock) -> None:
        mock_search.return_value = make_raw_offers("69123")

        response = self.client.get("/?mots_cles=data&territoire_type=commune&territoire=69123&distance=20")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_search.call_args.kwargs["commune"], "69123")
        self.assertEqual(mock_search.call_args.kwargs["distance"], 20)
        self.assertIn("2 offres trouvées pour la commune 69123", body)
        self.assertIn('<option value="commune" selected>', body)

    @patch("src.web_app.load_raw_offers", return_value=make_raw_offers("75"))
    @patch("src.web_app.load_market_context_rows", return_value=[])
    @patch("src.web_app.iter_search_offres")
    def test_department_search_forwards_filters(self, mock_search: Mock, _mock_context: Mock, _mock_raw: Mock) -> None:
        mock_search.return_value = make_raw_offers("75")

        response = self.client.get("/?mots_cles=ia&territoire_type=departement&territoire=75")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_search.call_args.kwargs["departement"], "75")
        self.assertIn("2 offres trouvées pour le département 75", body)

    @patch("src.web_app.load_raw_offers", return_value=make_raw_offers("84"))
    @patch("src.web_app.load_market_context_rows", return_value=[])
    @patch("src.web_app.iter_search_offres")
    def test_region_search_forwards_filters(self, mock_search: Mock, _mock_context: Mock, _mock_raw: Mock) -> None:
        mock_search.return_value = make_raw_offers("84")

        response = self.client.get("/?mots_cles=ia&territoire_type=region&territoire=84")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_search.call_args.kwargs["region"], "84")
        self.assertIn("2 offres trouvées pour la région 84", body)

    @patch("src.web_app.load_raw_offers", return_value=[])
    @patch("src.web_app.load_market_context_rows", return_value=[])
    @patch("src.web_app.iter_search_offres", side_effect=RuntimeError("API indisponible"))
    def test_api_error_is_rendered_without_traceback(self, _mock_search: Mock, _mock_context: Mock, _mock_raw: Mock) -> None:
        response = self.client.get("/?mots_cles=python")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("API indisponible", body)
        self.assertNotIn("Traceback", body)

    @patch("src.web_app.load_raw_offers", return_value=[])
    @patch("src.web_app.load_market_context_rows", return_value=[])
    @patch("src.web_app.iter_search_offres", return_value=[])
    def test_empty_page_state(self, _mock_search: Mock, _mock_context: Mock, _mock_raw: Mock) -> None:
        response = self.client.get("/?mots_cles=python")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Aucune offre ne correspond à cette recherche", body)

    @patch("src.web_app.compute_match")
    @patch("src.web_app._current_profile_snapshot")
    @patch("src.web_app._current_user_id", return_value=1)
    @patch("src.web_app.load_raw_offers", return_value=[])
    @patch("src.web_app.load_market_context_rows", return_value=[])
    @patch("src.web_app.iter_search_offres")
    def test_search_results_are_sorted_by_best_match_score_first(self, mock_search: Mock, _mock_context: Mock, _mock_raw: Mock, _mock_user_id: Mock, mock_profile: Mock, mock_match: Mock) -> None:
        raw_offers = [
            {
                "id": "high",
                "intitule": "Développeur Python senior",
                "titre": "Développeur Python senior",
                "competences": [{"libelle": "Python"}],
                "typeContratLibelle": "CDI",
                "lieuTravail": {"libelle": "Lyon", "commune": "Lyon", "codePostal": "69000"},
                "origineOffre": {"urlOrigine": "https://example.com/high"},
                "entreprise": {"nom": "ACME"},
            },
            {
                "id": "low",
                "intitule": "Chef de projet",
                "titre": "Chef de projet",
                "competences": [{"libelle": "Excel"}],
                "typeContratLibelle": "CDD",
                "lieuTravail": {"libelle": "Paris", "commune": "Paris", "codePostal": "75000"},
                "origineOffre": {"urlOrigine": "https://example.com/low"},
                "entreprise": {"nom": "Beta"},
            },
        ]
        mock_search.return_value = raw_offers

        def _match_side_effect(profile, offer, weights=None):
            score = 92.0 if offer.get("id") == "high" else 18.0
            return {
                "global_score": score,
                "matching_skills": ["Python"] if offer.get("id") == "high" else [],
                "criterion_scores": {},
                "criterion_details": {},
                "matching_weights": weights or {},
                "offer": offer,
                "score_global": score,
                "source": "France Travail",
                "url_originale": offer.get("origineOffre", {}).get("urlOrigine"),
                "competences_manquantes": [],
                "sous_scores": {},
            }

        mock_match.side_effect = _match_side_effect
        mock_profile.return_value = {
            "skills": [{"name": "Python", "normalized_name": "Python", "level": "expert", "years_experience": 5, "source": "manual"}],
            "desired_jobs": [{"job_title": "Développeur Python", "normalized_job_title": "developpeur python"}],
            "experiences": [],
            "diplomas": [],
            "city": "Lyon",
            "postal_code": "69000",
            "department": "69",
            "search_radius_km": 20,
            "remote_preference": "indifferent",
            "minimum_salary": 45000,
            "contract_preference": "CDI",
            "summary": "",
            "availability": "",
            "first_name": "Alice",
            "last_name": "Martin",
            "cv": None,
        }

        response = self.client.get("/?mots_cles=python&territoire_type=all")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertLess(body.index("Développeur Python senior"), body.index("Chef de projet"))


if __name__ == "__main__":
    unittest.main()
