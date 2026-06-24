# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests pour la normalisation territoriale et le filtrage."""

from __future__ import annotations

import unittest
from typing import Any, Dict

from src.territory_normalization import (
    extract_offer_territory_keys,
    extract_territory_code,
    filter_offers_by_territory,
    find_territory_key_in_data,
    normalize_territory,
    offer_matches_territory,
)


class NormalizeTerritoryTest(unittest.TestCase):
    """Tests pour normalize_territory."""

    def test_basic_city(self) -> None:
        self.assertEqual(normalize_territory("Paris"), "paris")

    def test_with_accents(self) -> None:
        self.assertEqual(normalize_territory("Île-de-France"), "ile-de-france")
        self.assertEqual(normalize_territory("Ile de France"), "ile-de-france")

    def test_department_code(self) -> None:
        self.assertEqual(normalize_territory("75"), "75")
        self.assertEqual(normalize_territory("69"), "69")

    def test_with_whitespace(self) -> None:
        self.assertEqual(normalize_territory("  Lyon  "), "lyon")

    def test_none(self) -> None:
        self.assertIsNone(normalize_territory(None))

    def test_empty(self) -> None:
        self.assertIsNone(normalize_territory(""))
        self.assertIsNone(normalize_territory("   "))

    def test_complex_territory(self) -> None:
        self.assertEqual(normalize_territory("75 - Paris 7e Arrondissement"), "75-paris-7e-arrondissement")


class ExtractTerritoryCodeTest(unittest.TestCase):
    """Tests pour extract_territory_code."""

    def test_department_code(self) -> None:
        self.assertEqual(extract_territory_code("75"), "75")
        self.assertEqual(extract_territory_code("69"), "69")

    def test_with_suffix(self) -> None:
        self.assertEqual(extract_territory_code("69 - LYON 01"), "69")
        self.assertEqual(extract_territory_code("75 - Paris 7e"), "75")

    def test_postal_code(self) -> None:
        self.assertEqual(extract_territory_code("75001"), "75001")

    def test_no_code(self) -> None:
        self.assertIsNone(extract_territory_code("Paris"))
        self.assertIsNone(extract_territory_code(""))


class ExtractOfferTerritoryKeysTest(unittest.TestCase):
    """Tests pour extract_offer_territory_keys."""

    def test_with_territoire_field(self) -> None:
        offer = {"territoire": "75 - Paris"}
        keys = extract_offer_territory_keys(offer)
        self.assertIn("75-paris", keys)
        self.assertIn("75", keys)

    def test_with_lieu_travail(self) -> None:
        offer = {
            "lieuTravail": {
                "libelle": "Lyon",
                "codePostal": "69001",
            }
        }
        keys = extract_offer_territory_keys(offer)
        self.assertIn("lyon", keys)
        self.assertIn("69001", keys)

    def test_with_ville(self) -> None:
        offer = {"ville": "Marseille"}
        keys = extract_offer_territory_keys(offer)
        self.assertIn("marseille", keys)

    def test_with_lieux_list(self) -> None:
        offer = {"lieux": ["Paris", "Lyon"]}
        keys = extract_offer_territory_keys(offer)
        self.assertIn("paris", keys)
        self.assertIn("lyon", keys)

    def test_empty_offer(self) -> None:
        offer = {}
        keys = extract_offer_territory_keys(offer)
        self.assertEqual(len(keys), 0)


class OfferMatchesTerritoryTest(unittest.TestCase):
    """Tests pour offer_matches_territory."""

    def test_no_territory_matches_all(self) -> None:
        offer = {"territoire": "Paris"}
        self.assertTrue(offer_matches_territory(offer, None))
        self.assertTrue(offer_matches_territory(offer, ""))

    def test_exact_match(self) -> None:
        offer = {"territoire": "Paris"}
        self.assertTrue(offer_matches_territory(offer, "Paris"))
        self.assertTrue(offer_matches_territory(offer, "paris"))

    def test_department_code_match(self) -> None:
        offer = {"territoire": "75 - Paris"}
        self.assertTrue(offer_matches_territory(offer, "75"))

    def test_no_match(self) -> None:
        offer = {"territoire": "Paris"}
        self.assertFalse(offer_matches_territory(offer, "Lyon"))

    def test_partial_match(self) -> None:
        offer = {"territoire": "75 - Paris 7e Arrondissement"}
        self.assertTrue(offer_matches_territory(offer, "Paris"))


class FilterOffersByTerritoryTest(unittest.TestCase):
    """Tests pour filter_offers_by_territory."""

    def test_no_filter(self) -> None:
        offers = [
            {"id": "1", "territoire": "Paris"},
            {"id": "2", "territoire": "Lyon"},
        ]
        result = filter_offers_by_territory(offers, None)
        self.assertEqual(len(result), 2)

    def test_filter_by_city(self) -> None:
        offers = [
            {"id": "1", "territoire": "Paris"},
            {"id": "2", "territoire": "Lyon"},
            {"id": "3", "territoire": "Paris"},
        ]
        result = filter_offers_by_territory(offers, "Paris")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "1")
        self.assertEqual(result[1]["id"], "3")

    def test_filter_by_department(self) -> None:
        offers = [
            {"id": "1", "territoire": "75 - Paris"},
            {"id": "2", "territoire": "69 - Lyon"},
        ]
        result = filter_offers_by_territory(offers, "75")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "1")


class FindTerritoryKeyInDataTest(unittest.TestCase):
    """Tests pour find_territory_key_in_data."""

    def test_exact_match(self) -> None:
        keys = ["global", "Paris", "Lyon"]
        self.assertEqual(find_territory_key_in_data("Paris", keys), "Paris")

    def test_case_insensitive(self) -> None:
        keys = ["global", "PARIS", "LYON"]
        self.assertEqual(find_territory_key_in_data("Paris", keys), "PARIS")

    def test_with_accents(self) -> None:
        keys = ["global", "Ile-de-France"]
        self.assertEqual(find_territory_key_in_data("Île-de-France", keys), "Ile-de-France")

    def test_department_code_match(self) -> None:
        keys = ["global", "75 - Paris", "69 - Lyon"]
        result = find_territory_key_in_data("75", keys)
        self.assertEqual(result, "75 - Paris")

    def test_partial_match(self) -> None:
        keys = ["global", "75 - Paris 7e Arrondissement"]
        result = find_territory_key_in_data("Paris", keys)
        self.assertEqual(result, "75 - Paris 7e Arrondissement")

    def test_no_match(self) -> None:
        keys = ["global", "Paris", "Lyon"]
        self.assertIsNone(find_territory_key_in_data("Marseille", keys))


if __name__ == "__main__":
    unittest.main()
