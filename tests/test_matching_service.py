# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from src.services.matching_service import compute_match, normalize_skill_name


class MatchingServiceTest(unittest.TestCase):
    def test_normalize_skill_name_merges_variants(self) -> None:
        self.assertEqual(normalize_skill_name("Python"), "Python")
        self.assertEqual(normalize_skill_name("Java Script"), "JavaScript")
        self.assertEqual(normalize_skill_name("Machine Learning"), "Machine learning")

    def test_compute_match_returns_bounded_score_and_explanation(self) -> None:
        profile = {
            "skills": [{"name": "Python"}, {"name": "Flask"}, {"name": "SQL"}],
            "desired_jobs": [{"job_title": "Développeur backend"}],
            "experiences": [{"job_title": "Développeur backend", "duration_years": 4}],
            "diplomas": [{"title": "Master Informatique"}],
            "city": "Lyon",
            "department": "69",
            "search_radius_km": 20,
            "remote_preference": "indifferent",
            "contract_preference": "CDI",
        }
        offer = {
            "id": "off-1",
            "titre": "Développeur backend Python",
            "entreprise": "ACME",
            "competences": ["Python", "Flask", "Docker"],
            "diplomes_requis": ["Master Informatique"],
            "contrat": "CDI",
            "teletravail": "hybride",
            "lieux": ["Lyon"],
            "experience_requise": "3 ans",
            "url_originale": "https://example.com/of-1",
            "source": "France Travail",
        }

        match = compute_match(profile, offer)

        self.assertGreaterEqual(match["global_score"], 0)
        self.assertLessEqual(match["global_score"], 100)
        self.assertIn("Python", match["matching_skills"])
        self.assertIn("Docker", match["missing_skills"])
        self.assertIn("summary", match["explanation"])
        self.assertIn("subscores", match["explanation"])


    def test_compute_match_uses_salary_and_location_details(self) -> None:
        profile = {
            "skills": [{"name": "Python"}],
            "desired_jobs": [{"job_title": "Développeur backend"}],
            "experiences": [{"job_title": "Développeur backend", "duration_years": 4}],
            "diplomas": [{"title": "Master Informatique"}],
            "city": "Lyon",
            "postal_code": "69000",
            "department": "69",
            "search_radius_km": 20,
            "minimum_salary": 50000,
            "remote_preference": "indifferent",
            "contract_preference": "CDI",
        }
        offer = {
            "id": "off-salary",
            "titre": "Développeur backend Python",
            "entreprise": "ACME",
            "competences": ["Python"],
            "diplomes_requis": ["Master Informatique"],
            "contrat": "CDI",
            "teletravail": "hybride",
            "lieux": ["Paris"],
            "salaire_min": 42000,
            "salaire_max": 46000,
            "experience_requise": "3 ans",
            "url_originale": "https://example.com/of-salary",
            "source": "France Travail",
        }

        match = compute_match(profile, offer)

        self.assertEqual(match["location_score"], 0.0)
        self.assertEqual(match["explanation"]["subscores"]["localisation"], 0.0)
        self.assertIn("localisation éloignée", match["criterion_details"]["localisation"]["reason"])
        self.assertEqual(match["salary_score"], 80.0)
        self.assertIn("salaire", match["criterion_details"])


    def test_compute_match_penalizes_distant_location(self) -> None:
        profile = {
            "skills": [{"name": "Python"}],
            "desired_jobs": [{"job_title": "Développeur backend"}],
            "experiences": [{"job_title": "Développeur backend", "duration_years": 4}],
            "diplomas": [{"title": "Master Informatique"}],
            "city": "Lyon",
            "postal_code": "69000",
            "department": "69",
            "search_radius_km": 20,
            "remote_preference": "indifferent",
            "contract_preference": "CDI",
        }
        offer = {
            "id": "off-remote",
            "titre": "Développeur backend Python",
            "entreprise": "ACME",
            "competences": ["Python"],
            "diplomes_requis": ["Master Informatique"],
            "contrat": "CDI",
            "teletravail": "presentiel",
            "lieux": ["Paris"],
            "experience_requise": "3 ans",
            "url_originale": "https://example.com/of-remote",
            "source": "France Travail",
        }

        match = compute_match(profile, offer)

        self.assertLessEqual(match["location_score"], 20)
        self.assertEqual(match["explanation"]["subscores"]["localisation"], match["location_score"])


if __name__ == "__main__":
    unittest.main()
