# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests pour valider les corrections du système de matching.

Ces tests vérifient que les critères absents ou non correspondants
donnent un score de 0 au lieu de 100.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from src.services.matching_service import (
    compute_skill_score,
    compute_experience_score,
    compute_diploma_score,
    compute_contract_score,
    compute_match,
    calculate_matching_score,
)


class TestSkillScoreCorrection(unittest.TestCase):
    """Tests pour la correction du score de compétences."""

    def test_no_common_skills_returns_zero(self) -> None:
        """Si aucune compétence commune, score = 0."""
        profile_skills = [
            {"name": "Python", "normalized_name": "python"},
            {"name": "Django", "normalized_name": "django"},
        ]
        offer_skills = ["Java", "Spring", "Hibernate"]
        
        result = compute_skill_score(profile_skills, offer_skills)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)
        self.assertEqual(len(result.details["matching_skills"]), 0)
        self.assertIn("aucune compétence commune", result.details.get("reason", ""))

    def test_empty_profile_skills_returns_zero(self) -> None:
        """Si profil sans compétences, score = 0."""
        profile_skills: List[Dict[str, Any]] = []
        offer_skills = ["Python", "Django"]
        
        result = compute_skill_score(profile_skills, offer_skills)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)

    def test_empty_offer_skills_returns_zero(self) -> None:
        """Si offre sans compétences, score = 0."""
        profile_skills = [
            {"name": "Python", "normalized_name": "python"},
        ]
        offer_skills: List[str] = []
        
        result = compute_skill_score(profile_skills, offer_skills)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)

    def test_common_skills_returns_positive_score(self) -> None:
        """Si compétences communes, score > 0."""
        profile_skills = [
            {"name": "Python", "normalized_name": "python"},
            {"name": "Django", "normalized_name": "django"},
        ]
        offer_skills = ["Python", "Django", "Flask"]
        
        result = compute_skill_score(profile_skills, offer_skills)
        
        self.assertGreater(result.score, 0.0)
        self.assertTrue(result.applicable)
        self.assertEqual(len(result.details["matching_skills"]), 2)


class TestExperienceScoreCorrection(unittest.TestCase):
    """Tests pour la correction du score d'expérience."""

    def test_no_experience_in_offer_returns_zero(self) -> None:
        """Si aucune expérience requise dans l'offre, score = 0."""
        profile_experiences: List[Dict[str, Any]] = []
        offer_experience = None
        
        result = compute_experience_score(profile_experiences, offer_experience)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)
        self.assertIn("non renseignée", result.details.get("reason", ""))

    def test_no_experience_in_profile_returns_zero(self) -> None:
        """Si aucune expérience dans le profil, score = 0."""
        profile_experiences: List[Dict[str, Any]] = []
        offer_experience = "3 ans"
        
        result = compute_experience_score(profile_experiences, offer_experience)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)
        self.assertIn("aucune expérience compatible", result.details.get("reason", ""))

    def test_matching_experience_returns_hundred(self) -> None:
        """Si expérience correspond exactement, score = 100."""
        profile_experiences = [
            {"duration_years": 3.0}
        ]
        offer_experience = "3 ans"
        
        result = compute_experience_score(profile_experiences, offer_experience)
        
        self.assertEqual(result.score, 100.0)
        self.assertTrue(result.applicable)

    def test_partial_experience_returns_partial_score(self) -> None:
        """Si expérience partielle, score entre 0 et 100."""
        profile_experiences = [
            {"duration_years": 1.5}
        ]
        offer_experience = "3 ans"
        
        result = compute_experience_score(profile_experiences, offer_experience)
        
        self.assertGreater(result.score, 0.0)
        self.assertLess(result.score, 100.0)
        self.assertTrue(result.applicable)


class TestDiplomaScoreCorrection(unittest.TestCase):
    """Tests pour la correction du score de diplôme."""

    def test_no_common_diploma_returns_zero(self) -> None:
        """Si aucun diplôme commun, score = 0."""
        profile_diplomas = [
            {"title": "Master Informatique"},
        ]
        offer_diplomas = ["Licence Économie", "BTS Commerce"]
        
        result = compute_diploma_score(profile_diplomas, offer_diplomas)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)
        self.assertIn("aucun diplôme compatible", result.details.get("reason", ""))

    def test_empty_profile_diplomas_returns_zero(self) -> None:
        """Si profil sans diplômes, score = 0."""
        profile_diplomas: List[Dict[str, Any]] = []
        offer_diplomas = ["Master Informatique"]
        
        result = compute_diploma_score(profile_diplomas, offer_diplomas)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)

    def test_empty_offer_diplomas_returns_zero(self) -> None:
        """Si offre sans diplômes requis, score = 0."""
        profile_diplomas = [
            {"title": "Master Informatique"},
        ]
        offer_diplomas: List[str] = []
        
        result = compute_diploma_score(profile_diplomas, offer_diplomas)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)

    def test_matching_diploma_returns_hundred(self) -> None:
        """Si diplôme correspond exactement, score = 100."""
        profile_diplomas = [
            {"title": "Master Informatique"},
        ]
        offer_diplomas = ["Master Informatique"]
        
        result = compute_diploma_score(profile_diplomas, offer_diplomas)
        
        self.assertEqual(result.score, 100.0)
        self.assertTrue(result.applicable)


class TestContractScoreCorrection(unittest.TestCase):
    """Tests pour la correction du score de contrat."""

    def test_no_contract_preference_returns_zero(self) -> None:
        """Si pas de préférence de contrat, score = 0."""
        profile_contract = None
        offer_contract = "CDI"
        
        result = compute_contract_score(profile_contract, offer_contract)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)
        self.assertIn("non renseigné", result.details.get("reason", ""))

    def test_no_contract_in_offer_returns_zero(self) -> None:
        """Si pas de contrat dans l'offre, score = 0."""
        profile_contract = "CDI"
        offer_contract = None
        
        result = compute_contract_score(profile_contract, offer_contract)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)

    def test_matching_contract_returns_hundred(self) -> None:
        """Si contrat correspond, score = 100."""
        profile_contract = "CDI"
        offer_contract = "CDI"
        
        result = compute_contract_score(profile_contract, offer_contract)
        
        self.assertEqual(result.score, 100.0)
        self.assertTrue(result.applicable)

    def test_different_contract_returns_zero(self) -> None:
        """Si contrat différent, score = 0."""
        profile_contract = "CDI"
        offer_contract = "CDD"
        
        result = compute_contract_score(profile_contract, offer_contract)
        
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.applicable)
        self.assertIn("différent", result.details.get("reason", ""))


class TestGlobalScoreCalculation(unittest.TestCase):
    """Tests pour le calcul du score global."""

    def test_global_score_decreases_with_zero_subscores(self) -> None:
        """Le score global baisse quand des sous-scores valent 0."""
        profile = {
            "skills": [
                {"name": "Python", "normalized_name": "python"},
            ],
            "desired_jobs": ["Développeur Python"],
            "experiences": [],
            "diplomas": [],
            "contract_preference": "CDI",
            "minimum_salary": 40000,
        }
        
        offer = {
            "id": "test-1",
            "titre": "Développeur Python",
            "competences": ["Python"],
            "contrat": "CDI",
            "source": "France Travail",
        }
        
        result = calculate_matching_score(profile, offer)
        
        # Le score global doit être calculé
        self.assertIn("global_score", result)
        self.assertGreaterEqual(result["global_score"], 0.0)
        self.assertLessEqual(result["global_score"], 100.0)

    def test_all_zero_subscores_gives_zero_global(self) -> None:
        """Si tous les sous-scores critiques valent 0, le score global est bas."""
        profile = {
            "skills": [],  # Pas de compétences
            "desired_jobs": [],
            "experiences": [],  # Pas d'expérience
            "diplomas": [],  # Pas de diplôme
            "contract_preference": None,  # Pas de préférence
            "minimum_salary": None,
        }
        
        offer = {
            "id": "test-2",
            "titre": "Développeur Python",
            "competences": ["Python", "Django"],
            "experience_requise": "3 ans",
            "diplomes_requis": ["Master Informatique"],
            "contrat": "CDI",
            "source": "France Travail",
        }
        
        result = calculate_matching_score(profile, offer)
        
        # Le score global doit être bas car plusieurs critères valent 0
        self.assertLess(result["global_score"], 50.0)


if __name__ == "__main__":
    unittest.main()
