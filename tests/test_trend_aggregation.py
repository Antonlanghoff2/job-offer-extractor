# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from src.trend_aggregation import aggregate_trends


class TrendAggregationTest(unittest.TestCase):
    def test_aggregation_includes_offres(self) -> None:
        offers = [
            {
                "id": "1",
                "date": "2026-06-17",
                "territoire": "Lyon",
                "ville": "Lyon",
                "metier": "Développeur IA",
                "niveau": "junior",
                "contrat": "CDI",
                "competences": ["Python", "SQL"],
                "intitule": "Développeur IA",
                "entreprise": "ACME",
                "url": "https://example.com/1",
            }
        ]

        result = aggregate_trends(offers, territoire="Lyon", periode_jours=30)

        self.assertEqual(result["nombre_offres"], 1)
        self.assertIn("offres", result)
        self.assertEqual(result["offres"][0]["id"], "1")
        self.assertEqual(result["offres"][0]["url"], "https://example.com/1")
        self.assertEqual(result["offers"], result["offres"])

    def test_territory_match_is_accent_insensitive(self) -> None:
        offers = [
            {
                "id": "2",
                "date": "2026-06-17",
                "territoire": "Région Bretagne",
                "metier": "Data Analyst",
                "niveau": "intermediaire",
                "contrat": "CDD",
                "competences": ["Python"],
                "intitule": "Data Analyst",
            }
        ]

        result = aggregate_trends(offers, territoire="region bretagne", periode_jours=30)
        self.assertEqual(result["nombre_offres"], 1)

    def test_territory_match_handles_lieux_embauche_lists(self) -> None:
        offers = [
            {
                "id": "3",
                "date": "2026-06-17",
                "lieux_embauche": ["Région Bretagne", "Rennes"],
                "metier": "Data Engineer",
                "niveau": "senior",
                "contrat": "CDI",
                "competences": ["Spark"],
                "intitule": "Data Engineer",
            }
        ]

        result = aggregate_trends(offers, territoire="region bretagne", periode_jours=30)
        self.assertEqual(result["nombre_offres"], 1)


if __name__ == "__main__":
    unittest.main()
