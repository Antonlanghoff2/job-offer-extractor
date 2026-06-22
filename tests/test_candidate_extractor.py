# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Tests pour l'extraction de candidats de compétences."""

from __future__ import annotations

import unittest

from src.skill_extraction.candidate_extractor import extract_candidates


class CandidateExtractorTest(unittest.TestCase):
    def test_action_verb_extracts_candidate(self) -> None:
        text = "Vous serez chargé de déployer les modèles en production."
        candidates = extract_candidates(text)
        self.assertTrue(len(candidates) > 0)
        candidate_texts = [c[0] for c in candidates]
        has_model_related = any("modèle" in c.lower() or "production" in c.lower() for c in candidate_texts)
        self.assertTrue(has_model_related, f"Candidats trouvés: {candidate_texts}")

    def test_noun_group_extraction(self) -> None:
        text = "Développement de pipelines de données et mise en place de processus ETL."
        candidates = extract_candidates(text)
        self.assertTrue(len(candidates) > 0)

    def test_competence_list_extraction(self) -> None:
        text = "Compétences : Python, Docker, gestion de projet"
        candidates = extract_candidates(text)
        candidate_texts = [c[0].lower() for c in candidates]
        self.assertTrue(
            any("python" in c for c in candidate_texts)
            or any("docker" in c for c in candidate_texts)
            or any("gestion" in c for c in candidate_texts),
            f"Candidats: {candidate_texts}",
        )

    def test_empty_text_returns_empty(self) -> None:
        self.assertEqual(extract_candidates(""), [])

    def test_source_sentence_is_preserved(self) -> None:
        text = "Vous développerez des APIs REST en Python."
        candidates = extract_candidates(text)
        for candidate_text, source_sentence in candidates:
            self.assertTrue(len(source_sentence) > 0)

    def test_false_positive_avoided(self) -> None:
        text = "Vous intégrerez une équipe dynamique dans un environnement stimulant."
        candidates = extract_candidates(text)
        candidate_texts = [c[0].lower() for c in candidates]
        self.assertNotIn("dynamique", candidate_texts)
        self.assertNotIn("environnement", candidate_texts)


if __name__ == "__main__":
    unittest.main()
