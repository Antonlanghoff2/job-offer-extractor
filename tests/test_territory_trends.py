# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.services.offer_repository import get_top_skills_by_territory
from src.web_app import create_app


def make_raw_offer(offer_id: str, title: str, territory: str, skills: list[str], date_creation: str = "2026-06-01") -> dict[str, object]:
    return {
        "id": offer_id,
        "intitule": title,
        "entreprise": {"nom": "ACME"},
        "lieuTravail": {"libelle": territory, "commune": territory, "codePostal": "69000"},
        "typeContratLibelle": "CDI",
        "dateCreation": date_creation,
        "description": "Description synthétique.",
        "competences": [{"libelle": skill} for skill in skills],
        "origineOffre": {"urlOrigine": f"https://example.com/{offer_id}"},
    }


def make_normalized_offer(
    offer_id: str,
    title: str,
    territory: str,
    skills: list[str],
    date_value: str = "2026-06-01",
) -> dict[str, object]:
    return {
        "id": offer_id,
        "intitule": title,
        "entreprise": "ACME",
        "territoire": territory,
        "ville": territory,
        "code_postal": "69000",
        "contrat": "CDI",
        "date_creation": date_value,
        "date": date_value,
        "url": f"https://example.com/{offer_id}",
        "description": "Description synthétique.",
        "metier": title,
        "niveau": "intermediaire",
        "competences": skills,
    }


def make_top_skill_dataset() -> list[dict[str, object]]:
    counts = [
        ("Alpha", 5),
        ("Beta", 4),
        ("Gamma", 3),
        ("Delta", 2),
        ("Epsilon", 2),
        ("Zeta", 1),
        ("Eta", 1),
        ("Theta", 1),
        ("Iota", 1),
        ("Kappa", 1),
        ("Lambda", 1),
        ("Mu", 1),
    ]
    offers: list[dict[str, object]] = []
    index = 1
    for skill, count in counts:
        for _ in range(count):
            offers.append(make_normalized_offer(str(index), f"Métier {skill}", "Lyon", [skill]))
            index += 1
    return offers


def make_case_fusion_dataset() -> list[dict[str, object]]:
    return [
        make_normalized_offer("1", "Développeur Python", "Lyon", ["Python", "python", " PYTHON ", "SQL", " SQL "]),
        make_normalized_offer("2", "Data Analyst", "Lyon", ["PYTHON", "SQL", "SQL", "Docker"]),
        make_normalized_offer("3", "Ingénieur IA", "Lyon", ["python", "Docker"]),
    ]


def make_selection_dataset() -> list[dict[str, object]]:
    return [
        make_normalized_offer("1", "Développeur Python", "Lyon", ["Python", "SQL"], "2026-06-01"),
        make_normalized_offer("2", "Développeur Go", "Paris", ["Go", "Docker"], "2026-06-02"),
    ]


class TerritoryTrendsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    @patch("src.web_app.load_normalized_offers", return_value=(make_selection_dataset(), None))
    @patch("src.web_app.iter_search_offres")
    def test_home_route_is_available_and_menu_is_visible(self, mock_search: Mock, _mock_offers: Mock) -> None:
        mock_search.return_value = [make_raw_offer("1", "Développeur Python", "Lyon", ["Python", "SQL"])]

        response = self.client.get("/?mots_cles=python")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Recherche d'offres d'emploi", body)
        self.assertIn("Recherche d'offres", body)
        self.assertIn("Tendances par territoire", body)
        self.assertIn("class=\"main-nav__link active\"", body)

    @patch("src.web_app.load_normalized_offers", return_value=(make_selection_dataset(), None))
    def test_territory_route_returns_200_and_respects_selection(self, _mock_offers: Mock) -> None:
        response = self.client.get("/tendances?territoire=Lyon")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Tendances par territoire", body)
        self.assertIn("Lyon", body)
        self.assertIn("Python", body)
        self.assertIn("SQL", body)
        self.assertIn("100,0 %", body)

    @patch("src.web_app.load_normalized_offers", return_value=(make_selection_dataset(), None))
    def test_territory_selection_changes_results(self, _mock_offers: Mock) -> None:
        lyon_response = self.client.get("/tendances?territoire=Lyon")
        paris_response = self.client.get("/tendances?territoire=Paris")

        lyon_body = lyon_response.get_data(as_text=True)
        paris_body = paris_response.get_data(as_text=True)

        self.assertIn("Python", lyon_body)
        self.assertIn("Go", paris_body)
        self.assertNotIn("Aucune compétence n’a été détectée", lyon_body)

    def test_skill_aggregation_limits_and_orders_results(self) -> None:
        rows = get_top_skills_by_territory(make_top_skill_dataset(), "Lyon", limit=10)

        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]["skill"], "Alpha")
        self.assertEqual(rows[1]["skill"], "Beta")
        self.assertEqual(rows[2]["skill"], "Gamma")
        self.assertEqual(rows[3]["skill"], "Delta")
        self.assertEqual(rows[4]["skill"], "Epsilon")
        self.assertEqual(rows[-1]["skill"], "Mu")
        self.assertGreaterEqual(rows[0]["count"], rows[1]["count"])
        self.assertGreaterEqual(rows[1]["count"], rows[2]["count"])
        self.assertGreater(rows[0]["count"], rows[1]["count"])

    def test_skill_aggregation_counts_each_skill_once_per_offer_and_merges_case(self) -> None:
        rows = get_top_skills_by_territory(make_case_fusion_dataset(), "Lyon", limit=10)
        python_row = next(item for item in rows if item["skill"] == "Python")
        sql_row = next(item for item in rows if item["skill"] == "SQL")
        docker_row = next(item for item in rows if item["skill"] == "Docker")

        self.assertEqual(python_row["count"], 3)
        self.assertEqual(sql_row["count"], 2)
        self.assertEqual(docker_row["count"], 2)
        self.assertAlmostEqual(sql_row["percentage"], 66.7)

    @patch("src.web_app.load_normalized_offers", return_value=([], None))
    def test_empty_state_is_rendered_without_error(self, _mock_offers: Mock) -> None:
        response = self.client.get("/tendances?territoire=Berlin")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Aucune compétence n’a été détectée pour ce territoire.", body)
        self.assertIn("Tous les territoires", body)

    @patch("src.web_app.load_normalized_offers", return_value=([], "Le fichier d'offres est invalide."))
    def test_invalid_data_does_not_trigger_http_500(self, _mock_offers: Mock) -> None:
        response = self.client.get("/tendances?territoire=Lyon")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Le fichier d'offres est invalide.", body)
        self.assertNotIn("Traceback", body)


if __name__ == "__main__":
    unittest.main()
