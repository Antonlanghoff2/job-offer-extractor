# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Tests pour le rapprochement sémantique des compétences."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from src.skill_extraction.semantic_matcher import (
    match_candidates_to_referential,
    reset_caches,
)


class SemanticMatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_caches()

    def tearDown(self) -> None:
        reset_caches()

    def test_semantic_match_for_data_engineering(self) -> None:
        candidates = [
            ("développement de flux de traitement et d'alimentation de données", "Vous développerez des flux de traitement et d'alimentation de données."),
        ]
        skills = match_candidates_to_referential(candidates)
        names = {s.canonical_name for s in skills}
        self.assertTrue(
            "Data Engineering" in names or "ETL" in names,
            f"Compétences trouvées: {names}",
        )

    def test_semantic_match_for_mlops(self) -> None:
        candidates = [
            ("déployer et surveiller les modèles en production", "Vous mettrez les modèles en production et surveillerez leur dérive."),
        ]
        skills = match_candidates_to_referential(candidates)
        names = {s.canonical_name for s in skills}
        self.assertTrue(
            "MLOps" in names or "Déploiement de modèles" in names or "Monitoring de modèles" in names,
            f"Compétences trouvées: {names}",
        )

    def test_empty_candidates_returns_empty(self) -> None:
        self.assertEqual(match_candidates_to_referential([]), [])

    def test_extraction_type_is_semantic_or_implicit(self) -> None:
        candidates = [
            ("développement de pipelines de données", "Vous développerez des pipelines."),
        ]
        skills = match_candidates_to_referential(candidates)
        for skill in skills:
            self.assertIn(skill.extraction_type, ("semantic", "implicit"))

    def test_confidence_is_bounded(self) -> None:
        candidates = [
            ("gestion de bases de données relationnelles", "Vous gérerez des bases de données."),
        ]
        skills = match_candidates_to_referential(candidates)
        for skill in skills:
            self.assertGreaterEqual(skill.confidence, 0.0)
            self.assertLessEqual(skill.confidence, 1.0)

    def test_referential_is_loaded_once(self) -> None:
        candidates = [
            ("développement de flux de traitement et d'alimentation de données", "Vous développerez des flux de traitement et d'alimentation de données."),
        ]
        from src.skill_extraction import referential_loader

        read_count = {"count": 0}
        original_read_text = Path.read_text

        def counting_read_text(self, *args, **kwargs):
            if self.name == "skills.json":
                read_count["count"] += 1
            return original_read_text(self, *args, **kwargs)

        referential_loader.clear_referential_cache()
        with patch.object(Path, "read_text", counting_read_text):
            match_candidates_to_referential(candidates)
            match_candidates_to_referential(candidates)

        self.assertEqual(read_count["count"], 1)


if __name__ == "__main__":
    unittest.main()
