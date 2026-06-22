# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Tests pour le pipeline hybride d'extraction de compétences."""

from __future__ import annotations

import unittest

from src.skill_extraction import ExtractedSkill, extract_skills_from_offer
from src.skill_extraction.semantic_matcher import reset_caches


class SkillPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_caches()

    def tearDown(self) -> None:
        reset_caches()

    def test_explicit_skills_detected(self) -> None:
        text = "Maîtrise de Python, Docker et PostgreSQL."
        skills = extract_skills_from_offer(text)
        names = {s.canonical_name for s in skills}
        self.assertIn("Python", names)
        self.assertIn("Docker", names)
        self.assertIn("PostgreSQL", names)

    def test_synonym_normalized(self) -> None:
        text = "Une bonne maîtrise de l'apprentissage automatique est demandée."
        skills = extract_skills_from_offer(text)
        names = {s.canonical_name for s in skills}
        self.assertIn("Machine learning", names)

    def test_deduplication(self) -> None:
        text = "Python est requis. Une solide expérience en développement Python est demandée."
        skills = extract_skills_from_offer(text)
        python_skills = [s for s in skills if s.canonical_name == "Python"]
        self.assertEqual(len(python_skills), 1)

    def test_negation_excludes_skill(self) -> None:
        text = "Aucune connaissance de Kubernetes n'est requise."
        skills = extract_skills_from_offer(text)
        k8s_skills = [s for s in skills if "kubernetes" in s.canonical_name.lower() and not s.negated]
        self.assertEqual(len(k8s_skills), 0)

    def test_false_positive_avoided(self) -> None:
        text = "Vous intégrerez une équipe dynamique dans un environnement stimulant."
        skills = extract_skills_from_offer(text)
        names = {s.canonical_name.lower() for s in skills}
        self.assertNotIn("dynamique", names)
        self.assertNotIn("environnement", names)

    def test_empty_text_returns_empty(self) -> None:
        self.assertEqual(extract_skills_from_offer(""), [])
        self.assertEqual(extract_skills_from_offer("   "), [])

    def test_implicit_skill_from_mission(self) -> None:
        text = "Vous mettrez les modèles en production et surveillerez leur dérive."
        skills = extract_skills_from_offer(text)
        names = {s.canonical_name for s in skills}
        has_mlops_related = any(
            name in names
            for name in ("MLOps", "Déploiement de modèles", "Monitoring de modèles", "Model drift")
        )
        self.assertTrue(has_mlops_related, f"Compétences trouvées: {names}")

    def test_each_skill_has_source_sentence(self) -> None:
        text = "Python et Docker sont requis. Vous développerez des APIs Flask."
        skills = extract_skills_from_offer(text)
        for skill in skills:
            self.assertTrue(len(skill.source_sentence) > 0, f"{skill.canonical_name} n'a pas de phrase source")

    def test_each_skill_has_confidence(self) -> None:
        text = "Python, Docker, PostgreSQL."
        skills = extract_skills_from_offer(text)
        for skill in skills:
            self.assertGreaterEqual(skill.confidence, 0.0)
            self.assertLessEqual(skill.confidence, 1.0)

    def test_extraction_type_priority(self) -> None:
        text = "Python est requis. Vous développerez en Python."
        skills = extract_skills_from_offer(text)
        python_skills = [s for s in skills if s.canonical_name == "Python"]
        if python_skills:
            self.assertEqual(python_skills[0].extraction_type, "explicit")

    def test_skill_to_dict(self) -> None:
        skill = ExtractedSkill(
            canonical_name="Python",
            raw_text="Python",
            source_sentence="Python est requis.",
            extraction_type="explicit",
            confidence=1.0,
            category="Langages",
        )
        d = skill.to_dict()
        self.assertEqual(d["canonical_name"], "Python")
        self.assertEqual(d["extraction_type"], "explicit")
        self.assertEqual(d["confidence"], 1.0)

    def test_semantic_match_data_engineering(self) -> None:
        text = "Vous développerez et maintiendrez des flux de traitement et d'alimentation de données."
        skills = extract_skills_from_offer(text)
        names = {s.canonical_name for s in skills}
        has_data_related = any(
            name in names
            for name in ("Data Engineering", "ETL", "Analyse de données")
        )
        self.assertTrue(has_data_related, f"Compétences trouvées: {names}")


if __name__ == "__main__":
    unittest.main()
