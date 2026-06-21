# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from src.ner.skill_entity_extractor import extract_skill_entities
from src.ner.skill_normalizer import canonicalize_skill_name, group_skill_variants, normalize_skill_name
from src.services.matching_service import compute_match
from src.trend_aggregation import aggregate_trends


class NerSkillPipelineTest(unittest.TestCase):
    def test_sentence_extraction_detects_python_and_flask(self) -> None:
        entities = extract_skill_entities("Je développe en Python3 avec Flask.")
        names = [entity.canonical_name for entity in entities]

        self.assertIn("Python", names)
        self.assertIn("Flask", names)

    def test_aliases_are_normalized_to_canonical_names(self) -> None:
        self.assertEqual(normalize_skill_name("IA"), "Intelligence artificielle")
        self.assertEqual(canonicalize_skill_name("développement Python"), "Python")
        self.assertEqual(canonicalize_skill_name("ML"), "Machine learning")

    def test_variants_are_grouped_under_the_same_canonical_skill(self) -> None:
        groups = group_skill_variants([
            "Python",
            "python3",
            "développement Python",
            "IA",
            "intelligence artificielle",
            "AI",
            "Artificial Intelligence",
            "machine learning",
            "ML",
        ])

        self.assertEqual(list(groups.keys()), ["Python", "Intelligence artificielle", "Machine learning"])
        self.assertEqual(groups["Python"], ["Python", "python3", "développement Python"])
        self.assertEqual(groups["Intelligence artificielle"], ["IA", "intelligence artificielle", "AI", "Artificial Intelligence"])
        self.assertEqual(groups["Machine learning"], ["machine learning", "ML"])

    def test_distinct_skills_are_not_fused_automatically(self) -> None:
        groups = group_skill_variants(["Java", "JavaScript", "SQL", "NoSQL", "C", "C++"])

        self.assertIn("Java", groups)
        self.assertIn("JavaScript", groups)
        self.assertIn("SQL", groups)
        self.assertIn("NoSQL", groups)
        self.assertIn("C", groups)
        self.assertIn("C++", groups)
        self.assertNotIn("JavaScript", groups.get("Java", []))
        self.assertNotIn("NoSQL", groups.get("SQL", []))
        self.assertNotIn("C++", groups.get("C", []))

    def test_matching_uses_normalized_skills(self) -> None:
        profile = {
            "skills": [
                {"name": "programmation Python"},
                {"name": "IA"},
            ],
            "desired_jobs": [{"job_title": "Développeur IA"}],
            "experiences": [],
            "diplomas": [],
            "remote_preference": "indifferent",
        }
        offer = {
            "id": "offer-ner-1",
            "titre": "Développeur Python et IA",
            "competences": ["Python3", "intelligence artificielle"],
            "contrat": "CDI",
            "url_originale": "https://example.org/offre/ner-1",
            "source": "demo",
        }

        result = compute_match(profile, offer)

        self.assertGreater(result["global_score"], 0)
        self.assertIn("Python", result["matching_skills"])
        self.assertIn("Intelligence artificielle", result["matching_skills"])

    def test_trend_statistics_group_close_variants(self) -> None:
        offers = [
            {
                "id": "1",
                "date": "2026-06-01",
                "territoire": "Lyon",
                "metier": "Développeur Python",
                "niveau": "intermediaire",
                "contrat": "CDI",
                "competences": ["Python", "python3", "développement Python"],
                "intitule": "Développeur Python",
            },
            {
                "id": "2",
                "date": "2026-06-02",
                "territoire": "Lyon",
                "metier": "Développeur Python",
                "niveau": "intermediaire",
                "contrat": "CDI",
                "competences": ["programmation Python", "Flask"],
                "intitule": "Développeur Python",
            },
            {
                "id": "3",
                "date": "2026-06-03",
                "territoire": "Lyon",
                "metier": "Ingénieur IA",
                "niveau": "senior",
                "contrat": "CDI",
                "competences": ["IA", "AI", "intelligence artificielle"],
                "intitule": "Ingénieur IA",
            },
        ]

        result = aggregate_trends(offers, territoire="Lyon", periode_jours=30)

        self.assertEqual(result["nombre_offres"], 3)
        self.assertEqual(result["competences"]["Python"], 2)
        self.assertEqual(result["competences"]["Intelligence artificielle"], 1)
        self.assertEqual(result["competences_variants"]["Python"]["Python"], 1)
        self.assertEqual(result["competences_variants"]["Python"]["python3"], 1)
        self.assertEqual(result["competences_variants"]["Python"]["développement Python"], 1)
        self.assertEqual(result["competences_variants"]["Intelligence artificielle"]["IA"], 1)
        self.assertEqual(result["competences_variants"]["Intelligence artificielle"]["AI"], 1)


if __name__ == "__main__":
    unittest.main()
