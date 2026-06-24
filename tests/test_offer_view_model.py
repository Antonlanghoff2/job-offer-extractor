# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests pour le ViewModel d'offre et les fonctions de résolution.

Couvre :
- Résolution du titre avec différents formats
- Résolution de la localisation
- Normalisation des sous-scores
- Construction du ViewModel
- Compatibilité avec les anciens formats
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from src.presentation.offer_view_model import (
    CACHE_SCHEMA_VERSION,
    OfferViewModel,
    build_match_view_model,
    build_offer_view_model,
    normalize_criterion_scores,
    resolve_offer_location,
    resolve_offer_title,
    resolve_offer_url,
)


class ResolveOfferTitleTest(unittest.TestCase):
    """Tests pour resolve_offer_title."""

    def test_title_field_present(self) -> None:
        offer = {"title": "Développeur Python"}
        self.assertEqual(resolve_offer_title(offer), "Développeur Python")

    def test_intitule_poste_fallback(self) -> None:
        offer = {"intitule_poste": "Chef de projet"}
        self.assertEqual(resolve_offer_title(offer), "Chef de projet")

    def test_intitule_fallback(self) -> None:
        offer = {"intitule": "Data Scientist H/F"}
        self.assertEqual(resolve_offer_title(offer), "Data Scientist H/F")

    def test_libelle_fallback(self) -> None:
        offer = {"libelle": "Ingénieur IA"}
        self.assertEqual(resolve_offer_title(offer), "Ingénieur IA")

    def test_metier_fallback(self) -> None:
        offer = {"metier": "Développeur full stack"}
        self.assertEqual(resolve_offer_title(offer), "Développeur full stack")

    def test_no_title_fallback(self) -> None:
        offer = {"entreprise": "ACME", "description": "text"}
        self.assertEqual(resolve_offer_title(offer), "Intitulé non renseigné")

    def test_empty_string_fallback(self) -> None:
        offer = {"title": "", "intitule": "  ", "metier": "Dev"}
        self.assertEqual(resolve_offer_title(offer), "Dev")

    def test_null_string_rejected(self) -> None:
        offer = {"title": "null", "intitule": "None", "metier": "Dev"}
        self.assertEqual(resolve_offer_title(offer), "Dev")

    def test_rome_libelle_fallback(self) -> None:
        offer = {"romeLibelle": "Développeur web"}
        self.assertEqual(resolve_offer_title(offer), "Développeur web")

    def test_not_a_dict(self) -> None:
        self.assertEqual(resolve_offer_title(None), "Intitulé non renseigné")
        self.assertEqual(resolve_offer_title("string"), "Intitulé non renseigné")

    def test_whitespace_stripped(self) -> None:
        offer = {"title": "  Dev Python  "}
        self.assertEqual(resolve_offer_title(offer), "Dev Python")

    def test_priority_order(self) -> None:
        offer = {
            "title": "Titre 1",
            "intitule_poste": "Titre 2",
            "intitule": "Titre 3",
            "metier": "Titre 4",
        }
        self.assertEqual(resolve_offer_title(offer), "Titre 1")


class ResolveOfferLocationTest(unittest.TestCase):
    """Tests pour resolve_offer_location."""

    def test_lieux_list(self) -> None:
        offer = {"lieux": ["Paris", "Lyon"]}
        self.assertEqual(resolve_offer_location(offer), "Paris, Lyon")

    def test_ville_fallback(self) -> None:
        offer = {"ville": "Marseille"}
        self.assertEqual(resolve_offer_location(offer), "Marseille")

    def test_territoire_fallback(self) -> None:
        offer = {"territoire": "75 - Paris"}
        self.assertEqual(resolve_offer_location(offer), "75 - Paris")

    def test_lieu_travail_dict(self) -> None:
        offer = {"lieuTravail": {"libelle": "Toulouse", "commune": "Toulouse"}}
        self.assertEqual(resolve_offer_location(offer), "Toulouse")

    def test_no_location(self) -> None:
        offer = {"title": "Dev"}
        self.assertEqual(resolve_offer_location(offer), "Lieu non renseigné")

    def test_code_postal_fallback(self) -> None:
        offer = {"code_postal": "75001"}
        self.assertEqual(resolve_offer_location(offer), "75001")


class ResolveOfferUrlTest(unittest.TestCase):
    """Tests pour resolve_offer_url."""

    def test_url_originale(self) -> None:
        offer = {"url_originale": "https://example.com/offer"}
        self.assertEqual(resolve_offer_url(offer), "https://example.com/offer")

    def test_url_field(self) -> None:
        offer = {"url": "https://example.com/offer"}
        self.assertEqual(resolve_offer_url(offer), "https://example.com/offer")

    def test_no_url_returns_none(self) -> None:
        offer = {"id": "123ABC", "source": "France Travail"}
        self.assertIsNone(resolve_offer_url(offer))

    def test_no_url(self) -> None:
        offer = {"title": "Dev"}
        self.assertIsNone(resolve_offer_url(offer))


class NormalizeCriterionScoresTest(unittest.TestCase):
    """Tests pour normalize_criterion_scores."""

    def test_empty_match(self) -> None:
        result = normalize_criterion_scores(None)
        self.assertIn("skills", result)
        self.assertFalse(result["skills"]["evaluated"])

    def test_sous_scores_format(self) -> None:
        match = {
            "sous_scores": {
                "competences": {
                    "score": 85.0,
                    "statut": "evalue",
                    "details": {"matching_skills": ["Python"]},
                },
                "metier": {
                    "score": None,
                    "statut": "champ_absent",
                    "details": {},
                },
            }
        }
        result = normalize_criterion_scores(match)
        self.assertTrue(result["skills"]["evaluated"])
        self.assertEqual(result["skills"]["score"], 85.0)
        self.assertEqual(result["skills"]["matched_values"], ["Python"])
        self.assertFalse(result["job"]["evaluated"])
        self.assertIsNone(result["job"]["score"])

    def test_criterion_scores_0_1_format(self) -> None:
        match = {
            "criterion_scores": {
                "competences": 0.85,
                "localisation": None,
            },
            "criterion_details": {
                "competences": {"matching_skills": ["Java"]},
            },
        }
        result = normalize_criterion_scores(match)
        self.assertTrue(result["skills"]["evaluated"])
        self.assertAlmostEqual(result["skills"]["score"], 85.0)

    def test_explanation_subscores_format(self) -> None:
        match = {
            "explanation": {
                "subscores": {
                    "competences": 80.0,
                    "salaire": 60.0,
                }
            }
        }
        result = normalize_criterion_scores(match)
        self.assertTrue(result["skills"]["evaluated"])
        self.assertEqual(result["skills"]["score"], 80.0)
        self.assertTrue(result["salary"]["evaluated"])
        self.assertEqual(result["salary"]["score"], 60.0)

    def test_score_field_fallback(self) -> None:
        match = {
            "skill_score": 75.0,
            "job_score": 50.0,
        }
        result = normalize_criterion_scores(match)
        self.assertTrue(result["skills"]["evaluated"])
        self.assertEqual(result["skills"]["score"], 75.0)
        self.assertTrue(result["job"]["evaluated"])
        self.assertEqual(result["job"]["score"], 50.0)

    def test_legacy_key_mapping(self) -> None:
        match = {
            "sous_scores": {
                "teletravail": {"score": 100.0, "statut": "evalue", "details": {}},
                "diplome": {"score": 50.0, "statut": "evalue", "details": {}},
            }
        }
        result = normalize_criterion_scores(match)
        self.assertTrue(result["remote"]["evaluated"])
        self.assertTrue(result["diploma"]["evaluated"])

    def test_zero_score_is_evaluated(self) -> None:
        match = {
            "sous_scores": {
                "competences": {"score": 0.0, "statut": "evalue", "details": {}},
            }
        }
        result = normalize_criterion_scores(match)
        self.assertTrue(result["skills"]["evaluated"])
        self.assertEqual(result["skills"]["score"], 0.0)

    def test_none_score_not_evaluated(self) -> None:
        match = {
            "sous_scores": {
                "competences": {"score": None, "statut": "champ_absent", "details": {}},
            }
        }
        result = normalize_criterion_scores(match)
        self.assertFalse(result["skills"]["evaluated"])
        self.assertIsNone(result["skills"]["score"])


class BuildOfferViewModelTest(unittest.TestCase):
    """Tests pour build_offer_view_model."""

    def test_basic_offer(self) -> None:
        offer = {
            "id": "123",
            "intitule": "Dev Python",
            "entreprise": "ACME",
            "ville": "Paris",
            "contrat": "CDI",
            "source": "France Travail",
        }
        vm = build_offer_view_model(offer)
        self.assertEqual(vm.offer_id, "123")
        self.assertEqual(vm.title, "Dev Python")
        self.assertEqual(vm.company, "ACME")
        self.assertEqual(vm.location, "Paris")
        self.assertEqual(vm.contract, "CDI")

    def test_no_title(self) -> None:
        offer = {"id": "1", "entreprise": "ACME"}
        vm = build_offer_view_model(offer)
        self.assertEqual(vm.title, "Intitulé non renseigné")

    def test_with_match_result(self) -> None:
        offer = {"id": "1", "intitule": "Dev"}
        match = {
            "global_score": 75.5,
            "matching_skills": ["Python"],
            "missing_skills": ["Java"],
            "sous_scores": {
                "competences": {"score": 85.0, "statut": "evalue", "details": {}},
            },
        }
        vm = build_offer_view_model(offer, match)
        self.assertEqual(vm.global_score, 75.5)
        self.assertEqual(vm.matched_skills, ["Python"])
        self.assertEqual(vm.missing_skills, ["Java"])
        self.assertIn("skills", vm.criterion_scores)

    def test_salary_text(self) -> None:
        offer = {"id": "1", "intitule": "Dev", "salaire_min": 35000, "salaire_max": 45000}
        vm = build_offer_view_model(offer)
        self.assertIn("35", vm.salary_text or "")
        self.assertIn("45", vm.salary_text or "")

    def test_remote_text(self) -> None:
        offer = {"id": "1", "intitule": "Dev", "teletravail": "hybride"}
        vm = build_offer_view_model(offer)
        self.assertEqual(vm.remote_text, "Télétravail hybride")


class BuildMatchViewModelTest(unittest.TestCase):
    """Tests pour build_match_view_model."""

    def test_from_cached_match(self) -> None:
        match = {
            "offer_id": "ABC123",
            "score": 80.0,
            "matching_skills": ["Python"],
            "missing_skills": [],
            "details": {
                "global_score": 80.0,
                "sous_scores": {
                    "competences": {"score": 90.0, "statut": "evalue", "details": {}},
                },
                "criterion_details": {},
                "explanation": {},
            },
        }
        offer = {"id": "ABC123", "intitule": "Dev Python", "ville": "Lyon"}
        vm = build_match_view_model(match, offer)
        self.assertEqual(vm.offer_id, "ABC123")
        self.assertEqual(vm.title, "Dev Python")
        self.assertEqual(vm.global_score, 80.0)
        self.assertTrue(vm.criterion_scores["skills"]["evaluated"])

    def test_from_direct_match(self) -> None:
        match = {
            "offer_identifier": "XYZ",
            "global_score": 65.0,
            "matching_skills": ["Java"],
            "missing_skills": ["Go"],
            "criterion_scores": {"competences": 0.7, "localisation": 0.8},
            "criterion_details": {},
            "explanation": {},
            "offer": {"id": "XYZ", "intitule": "Dev Java", "territoire": "Paris"},
        }
        vm = build_match_view_model(match)
        self.assertEqual(vm.title, "Dev Java")
        self.assertEqual(vm.global_score, 65.0)


class CacheSchemaVersionTest(unittest.TestCase):
    """Tests pour le versioning du cache."""

    def test_schema_version_is_int(self) -> None:
        self.assertIsInstance(CACHE_SCHEMA_VERSION, int)
        self.assertGreaterEqual(CACHE_SCHEMA_VERSION, 2)


if __name__ == "__main__":
    unittest.main()
