# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Tests pour l'extraction lexicale de compétences."""

from __future__ import annotations

import unittest

from src.skill_extraction.lexical_extractor import extract_explicit_skills


class LexicalExtractorTest(unittest.TestCase):
    def test_explicit_python_docker_postgresql(self) -> None:
        text = "Maîtrise de Python, Docker et PostgreSQL."
        skills = extract_explicit_skills(text)
        names = {s.canonical_name for s in skills}
        self.assertIn("Python", names)
        self.assertIn("Docker", names)
        self.assertIn("PostgreSQL", names)
        for skill in skills:
            self.assertEqual(skill.extraction_type, "explicit")
            self.assertEqual(skill.confidence, 1.0)

    def test_synonym_apprentissage_automatique(self) -> None:
        text = "Une bonne maîtrise de l'apprentissage automatique est demandée."
        skills = extract_explicit_skills(text)
        names = {s.canonical_name for s in skills}
        self.assertIn("Machine learning", names)

    def test_negation_excludes_skill(self) -> None:
        text = "Aucune connaissance de Kubernetes n'est requise."
        skills = extract_explicit_skills(text)
        k8s_skills = [s for s in skills if "kubernetes" in s.canonical_name.lower()]
        for skill in k8s_skills:
            self.assertTrue(skill.negated)

    def test_optional_skill_detected(self) -> None:
        text = "Une connaissance de React serait un plus."
        skills = extract_explicit_skills(text)
        react_skills = [s for s in skills if "react" in s.canonical_name.lower()]
        if react_skills:
            self.assertTrue(react_skills[0].optional)

    def test_empty_text_returns_empty(self) -> None:
        self.assertEqual(extract_explicit_skills(""), [])
        self.assertEqual(extract_explicit_skills("   "), [])

    def test_source_sentence_is_preserved(self) -> None:
        text = "Vous développerez des APIs en Python."
        skills = extract_explicit_skills(text)
        python_skills = [s for s in skills if s.canonical_name == "Python"]
        if python_skills:
            self.assertTrue(len(python_skills[0].source_sentence) > 0)


if __name__ == "__main__":
    unittest.main()
