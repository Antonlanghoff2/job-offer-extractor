# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from src.profile_extraction.experience_skill_extractor import extract_skills_from_experience


class ExperienceSkillExtractorTest(unittest.TestCase):
    def test_extracts_skills_from_title_and_description(self) -> None:
        skills = extract_skills_from_experience(
            "Développeur backend Python",
            "Développement d'API REST avec Flask, PostgreSQL, Docker et Git. Mise en place de tests automatisés.",
        )
        names = {skill["name"] for skill in skills}

        self.assertIn("Python", names)
        self.assertIn("Flask", names)
        self.assertIn("PostgreSQL", names)
        self.assertIn("Docker", names)
        self.assertIn("Git", names)
        self.assertIn("API REST", names)
        self.assertIn("Développement d'API", names)
        self.assertIn("Tests automatisés", names)
        self.assertNotIn("Développeur backend Python", names)

    def test_extracts_from_description_only(self) -> None:
        skills = extract_skills_from_experience(
            "",
            "Installation et exploitation d'un réseau audio Dante, mixage sur console numérique et maintenance du parc.",
        )
        names = {skill["name"] for skill in skills}

        self.assertIn("Dante", names)
        self.assertIn("Réseau audio", names)
        self.assertIn("Mixage audio", names)
        self.assertIn("Console numérique", names)
        self.assertIn("Maintenance technique", names)

    def test_normalizes_variants_and_filters_existing_skills(self) -> None:
        skills = extract_skills_from_experience(
            "Ingénieur DevOps",
            "Déploiement sur GitLab CI et administration PostgreSQL avec Python3 et machine-learning.",
            existing_skills=["Python", "PostgreSQL"],
        )
        names = {skill["name"] for skill in skills}

        self.assertNotIn("Python", names)
        self.assertNotIn("PostgreSQL", names)
        self.assertIn("GitLab CI/CD", names)
        self.assertIn("Machine learning", names)

    def test_does_not_invent_generic_verbs(self) -> None:
        skills = extract_skills_from_experience(
            "Chef de projet",
            "Participer aux réunions, travailler en équipe et contribuer au suivi.",
        )
        names = {skill["name"] for skill in skills}

        self.assertNotIn("Participer", names)
        self.assertNotIn("Travailler", names)
        self.assertNotIn("Contribuer", names)


if __name__ == "__main__":
    unittest.main()
