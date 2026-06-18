# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from src.offer_normalization import normalize_france_travail_offer


class OfferNormalizationTest(unittest.TestCase):
    def test_complete_offer_prefers_origin_url(self) -> None:
        offer = {
            "id": "123",
            "intitule": "Développeur Python",
            "entreprise": {"nom": "ACME"},
            "lieuTravail": {"libelle": "69 - Lyon", "commune": "69381", "codePostal": "69000"},
            "typeContratLibelle": "CDI",
            "dateCreation": "2026-06-17T10:00:00Z",
            "origineOffre": {"urlOrigine": "https://example.com/origine"},
            "description": "Une offre complète.",
        }

        normalized = normalize_france_travail_offer(offer)

        self.assertEqual(normalized["id"], "123")
        self.assertEqual(normalized["intitule"], "Développeur Python")
        self.assertEqual(normalized["entreprise"], "ACME")
        self.assertEqual(normalized["territoire"], "69 - Lyon")
        self.assertEqual(normalized["ville"], "69381")
        self.assertEqual(normalized["code_postal"], "69000")
        self.assertEqual(normalized["contrat"], "CDI")
        self.assertEqual(normalized["date_creation"], "2026-06-17")
        self.assertEqual(normalized["url"], "https://example.com/origine")
        self.assertEqual(normalized["description"], "Une offre complète.")

    def test_fallback_url_uses_identifier(self) -> None:
        normalized = normalize_france_travail_offer({"id": "456"})
        self.assertEqual(
            normalized["url"],
            "https://candidat.francetravail.fr/offres/recherche/detail/456",
        )

    def test_missing_origin_and_identifier_returns_none(self) -> None:
        normalized = normalize_france_travail_offer({"intitule": "Sans id"})
        self.assertIsNone(normalized["url"])

    def test_missing_fields_are_tolerated(self) -> None:
        normalized = normalize_france_travail_offer({})
        self.assertEqual(normalized["id"], "")
        self.assertEqual(normalized["intitule"], "")
        self.assertEqual(normalized["entreprise"], "")
        self.assertEqual(normalized["territoire"], "")
        self.assertEqual(normalized["ville"], "")
        self.assertEqual(normalized["code_postal"], "")
        self.assertEqual(normalized["contrat"], "")
        self.assertEqual(normalized["date_creation"], "")
        self.assertIsNone(normalized["url"])
        self.assertEqual(normalized["description"], "")


if __name__ == "__main__":
    unittest.main()
