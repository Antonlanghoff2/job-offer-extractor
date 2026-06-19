# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.web_app import create_app


def make_raw_offers(territoire: str) -> list[dict[str, object]]:
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


if __name__ == "__main__":
    unittest.main()
