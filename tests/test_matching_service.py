# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from src.services.matching_service import compute_match, normalize_skill_name


class MatchingServiceTest(unittest.TestCase):
    def test_normalize_skill_name_merges_variants(self) -> None:
        self.assertEqual(normalize_skill_name("Python"), "python")
        self.assertEqual(normalize_skill_name("Java Script"), "javascript")
        self.assertEqual(normalize_skill_name("Machine Learning"), "machinelearning")

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


if __name__ == "__main__":
    unittest.main()
